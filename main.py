from __future__ import annotations

import asyncio
import signal
import time
from contextlib import suppress

from broker.delta_client import (
    DeltaAPIError,
    DeltaClient,
    is_recoverable_entry_order_error,
    isolated_margin_rejection_hint,
)
from broker.order_manager import OrderManager
from broker.websocket_client import DeltaWebSocketClient
from strategy.risk_manager import RiskManager
from strategy.signal_generator import SignalGenerator
from ui.dashboard import Dashboard
from utils.helpers import (
    BotMonitorSnapshot,
    BotShutdown,
    Candle,
    CriticalBotError,
    ExchangePositionOverview,
    SymbolMonitorState,
    active_trading_symbols,
    ensure_directories,
    instrument_settings,
    load_config,
    timeframe_summary,
    normalize_candle_timestamp,
    system_usage,
    timeframe_to_seconds,
    unix_seconds,
)
from utils.logger import log_snapshot, setup_logging
from utils.timezone_helper import format_ist, is_time_between
from utils.trade_tracker import TradeTracker


class TradingBot:
    def __init__(self) -> None:
        ensure_directories()
        self.config = load_config()
        self.loggers = setup_logging(self.config)
        exchange = self.config["exchange"]
        trading = self.config["trading"]
        system = self.config["system"]
        self.symbols = active_trading_symbols(self.config)
        if not self.symbols:
            raise CriticalBotError("No enabled trading symbols in config (trading.instruments)")
        self.client = DeltaClient(exchange["base_url"], exchange.get("api_key", ""), exchange.get("api_secret", ""))
        self.tracker = TradeTracker()
        self.order_manager = OrderManager(self.config, self.client, self.tracker, self.loggers["trading"])
        self.risk_manager = RiskManager(self.config, self.tracker)
        self.signal_generator = SignalGenerator(self.config)
        self.dashboard = Dashboard(enabled=bool(system.get("dashboard_enabled", True)))
        timeframe_by_symbol = {
            sym: instrument_settings(self.config, sym).timeframe for sym in self.symbols
        }
        self.websocket = DeltaWebSocketClient(
            websocket_url=exchange["websocket_url"],
            symbols=self.symbols,
            timeframe_by_symbol=timeframe_by_symbol,
            retry_count=int(system["retry_count"]),
            retry_delay=int(system["retry_delay"]),
            history_limit=int(system.get("candle_history_limit", 200)),
            logger=self.loggers["system"],
        )
        self._stop = asyncio.Event()
        self._started_at = time.time()

    async def run(self) -> None:
        self._install_signal_handlers()
        interval = int(self.config["signal_engine"]["signal_check_interval_seconds"])
        self.dashboard.start(self.symbols)
        await self.client.open()
        if self.config["system"].get("websocket_enabled", True):
            self.websocket.start()

        try:
            while not self._stop.is_set():
                started = time.time()
                if not is_time_between(
                    self.config["session"]["trading_start_time"],
                    self.config["session"]["trading_end_time"],
                ):
                    self.loggers["system"].info("Outside trading session; waiting for next cycle")
                else:
                    exchange_overview = await self._exchange_overview()
                    symbol_states: list[SymbolMonitorState] = []
                    for symbol in self.symbols:
                        if self._stop.is_set():
                            break
                        state = await self._process_symbol(symbol, exchange_overview)
                        if state is not None:
                            symbol_states.append(state)

                    if symbol_states:
                        snapshot = self._build_bot_snapshot(symbol_states, exchange_overview, interval)
                        log_snapshot(self.loggers["trading"], snapshot)
                        self.dashboard.update(snapshot)

                elapsed = time.time() - started
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self._stop.wait(), timeout=max(interval - elapsed, 1))
        except CriticalBotError as exc:
            self.loggers["error"].error(str(exc))
            self.dashboard.alert(str(exc))
            raise
        except BotShutdown:
            raise
        except Exception as exc:
            self.loggers["error"].exception("Unexpected bot failure: %s", exc)
            self.dashboard.alert(f"Unexpected bot failure: {exc}")
            raise
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        self._stop.set()
        with suppress(Exception):
            await self.websocket.stop()
        with suppress(Exception):
            await self.client.close()
        self.dashboard.stop()
        self.loggers["system"].info("Bot shutdown complete")

    async def _exchange_overview(self) -> ExchangePositionOverview:
        if not self.config["system"].get("dashboard_exchange_positions", True):
            return ExchangePositionOverview(source="off")
        if self.order_manager.paper_trading:
            return ExchangePositionOverview(source="paper")
        prices: dict[str, float] = {}
        for sym in self.symbols:
            p = self.websocket.latest_price(sym)
            if p and p > 0:
                prices[sym] = float(p)
        return await self.order_manager.load_exchange_positions(prices)

    async def _process_symbol(
        self,
        symbol: str,
        exchange_overview: ExchangePositionOverview,
    ) -> SymbolMonitorState | None:
        self.websocket.raise_if_failed()
        settings = instrument_settings(self.config, symbol)
        candles = await self._get_candles(symbol, settings.timeframe)
        timeframe = settings.timeframe
        signal_candles = _completed_candles(candles, timeframe)
        if len(signal_candles) < 2:
            self.loggers["system"].warning("Not enough candle data for %s", symbol)
            return None

        forming = _forming_candle(candles, timeframe)
        current_price = self.websocket.latest_price(symbol) or candles[-1].close
        position = self.order_manager.position_for(symbol)

        await self.order_manager.validate_exit(symbol, current_price)
        position = self.order_manager.position_for(symbol)

        any_active = self.order_manager.active_position_count > 0
        self.risk_manager.validate_daily_limits(any_active)

        indicators, decision = self.signal_generator.evaluate(
            signal_candles,
            position,
            forming,
            current_price,
        )

        if decision.should_trade and not self.risk_manager.can_open_new_trade():
            decision.action = "hold"
            decision.status = "SIGNAL_REJECTED"
            decision.rejected_reason = (
                f"daily trade limit reached "
                f"({self.risk_manager.trades_today()}/{self.risk_manager.max_trades_per_day()})"
            )
        if decision.should_trade and self.risk_manager.validate_open_position_limit(
            self.order_manager.active_position_count
        ):
            try:
                await self.order_manager.open_position(symbol, decision.action, current_price)
            except DeltaAPIError as exc:
                msg = str(exc)
                if is_recoverable_entry_order_error(msg):
                    hint = isolated_margin_rejection_hint(msg)
                    self.loggers["trading"].warning("Entry order rejected by Delta: %s", msg)
                    if hint:
                        self.loggers["trading"].warning("%s", hint)
                    panel = hint or msg
                    self.dashboard.alert(f"{symbol}: entry skipped — {panel[:400]}", style="bold yellow")
                else:
                    raise
            else:
                self.signal_generator.mark_trade_executed(symbol)

        position = self.order_manager.position_for(symbol)
        return SymbolMonitorState(
            symbol=symbol,
            timeframe=timeframe,
            current_price=current_price,
            current_candle=signal_candles[-1],
            previous_candle=signal_candles[-2],
            indicators=indicators,
            signal=decision,
            position=position,
            realized_pnl_today=self.tracker.daily_realized_pnl(symbol),
            forming_candle=forming,
        )

    def _build_bot_snapshot(
        self,
        symbol_states: list[SymbolMonitorState],
        exchange_overview: ExchangePositionOverview,
        interval: int,
    ) -> BotMonitorSnapshot:
        usage = system_usage()
        total_unrealized = sum(
            s.position.unrealized_pnl for s in symbol_states if s.position.active
        )
        total_realized_today = sum(s.realized_pnl_today for s in symbol_states)
        daily_pnl = self.risk_manager.daily_pnl()

        return BotMonitorSnapshot(
            timeframe=timeframe_summary(self.config, [s.symbol for s in symbol_states]),
            symbols=symbol_states,
            trades_today=self.risk_manager.trades_today(),
            closed_trades_today=self.risk_manager.closed_trades_today(),
            max_trades_per_day=int(self.config["risk_management"]["max_trades_per_day"]),
            daily_pnl=daily_pnl,
            daily_loss_limit=float(self.config["risk_management"]["daily_loss_limit"]),
            total_unrealized_pnl=total_unrealized,
            total_realized_today=total_realized_today,
            overall_pnl=daily_pnl + total_unrealized,
            api_status="HEALTHY",
            websocket_status=self.websocket.status(),
            last_signal_check=format_ist(),
            next_signal_check_seconds=interval,
            running_seconds=int(time.time() - self._started_at),
            memory_mb=usage["memory_mb"],
            cpu_load_1m=usage["cpu_load_1m"],
            exchange_positions=exchange_overview,
        )

    async def _get_candles(self, symbol: str, timeframe: str) -> list[Candle]:
        candles = self.websocket.candles(symbol)
        min_required = max(
            int(self.config["bollinger_bands"]["bb_length"]),
            int(self.config["rsi"]["rsi_length"]),
        ) + 3
        if len(candles) >= min_required:
            return candles

        resolution = timeframe
        candle_seconds = timeframe_to_seconds(resolution)
        end = unix_seconds()
        start = end - candle_seconds * int(self.config["system"].get("candle_history_limit", 200))
        raw_candles = await self.client.get_candles(symbol, resolution, start, end)
        backfill = [_parse_candle(item, resolution) for item in raw_candles]
        return _merge_candles(backfill, candles)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.request_stop)

    def request_stop(self) -> None:
        self.loggers["system"].info("Shutdown requested")
        self._stop.set()


def _parse_candle(item: dict, timeframe: str) -> Candle:
    return Candle(
        timestamp=normalize_candle_timestamp(int(item.get("time") or item.get("timestamp") or 0), timeframe),
        open=float(item.get("open", 0)),
        high=float(item.get("high", 0)),
        low=float(item.get("low", 0)),
        close=float(item.get("close", 0)),
        volume=float(item.get("volume", 0)),
    )


def _merge_candles(backfill: list[Candle], websocket_candles: list[Candle]) -> list[Candle]:
    candles_by_timestamp = {candle.timestamp: candle for candle in backfill}
    candles_by_timestamp.update({candle.timestamp: candle for candle in websocket_candles})
    return [candles_by_timestamp[timestamp] for timestamp in sorted(candles_by_timestamp)]


def _completed_candles(candles: list[Candle], timeframe: str, now: int | None = None) -> list[Candle]:
    current_bucket = normalize_candle_timestamp(now or unix_seconds(), timeframe)
    return [candle for candle in candles if candle.timestamp < current_bucket]


def _forming_candle(candles: list[Candle], timeframe: str, now: int | None = None) -> Candle | None:
    """Current in-progress bar from the feed, if present (same timestamp as current bucket)."""
    if not candles:
        return None
    bucket = normalize_candle_timestamp(now or unix_seconds(), timeframe)
    last = candles[-1]
    if last.timestamp >= bucket:
        return last
    return None


async def async_main() -> int:
    bot = TradingBot()
    try:
        await bot.run()
        return 0
    except CriticalBotError:
        return 1


def main() -> int:
    return asyncio.run(async_main())


if __name__ == "__main__":
    raise SystemExit(main())
