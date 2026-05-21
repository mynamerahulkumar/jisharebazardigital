from __future__ import annotations

import logging

from broker.bracket_prices import compute_bracket_limit_prices, validate_bracket_prices
from broker.delta_client import DeltaAPIError, DeltaClient
from broker.exchange_positions import margined_positions_to_overview, open_position_product_ids
from utils.helpers import CriticalBotError, ExchangePositionOverview, PositionState, instrument_settings
from utils.timezone_helper import format_ist, today_ist
from utils.trade_tracker import TradeRecord, TradeTracker


def _price_to_api_str(price: float) -> str:
    s = f"{price:.12f}".rstrip("0").rstrip(".")
    return s if s else "0"


def _round_to_tick(price: float, tick: float) -> float:
    if tick <= 0:
        return price
    return round(price / tick) * tick


class OrderManager:
    def __init__(
        self,
        config: dict,
        client: DeltaClient,
        tracker: TradeTracker,
        logger: logging.Logger,
    ) -> None:
        self.config = config
        self.client = client
        self.tracker = tracker
        self.logger = logger
        self.positions: dict[str, PositionState] = {}
        self._contract_value_cache: dict[int, float] = {}
        self._tick_size_cache: dict[int, float] = {}

    def position_for(self, symbol: str) -> PositionState:
        return self.positions.get(symbol, PositionState(symbol=symbol))

    @property
    def active_position_count(self) -> int:
        return sum(1 for p in self.positions.values() if p.active)

    async def _resolve_contract_value(self, product_id: int, symbol: str) -> float:
        if product_id in self._contract_value_cache:
            return self._contract_value_cache[product_id]
        cfg = self.config.get("trading", {}).get("contract_value_by_symbol") or {}
        if symbol in cfg:
            v = float(cfg[symbol])
            self._contract_value_cache[product_id] = v
            return v
        try:
            prod = await self.client.get_product(symbol)
            if isinstance(prod, list) and prod:
                prod = prod[0]
            if not isinstance(prod, dict):
                self._contract_value_cache[product_id] = 1.0
                return 1.0
            v = float(prod.get("contract_value", 1.0))
            self._contract_value_cache[product_id] = v
            return v
        except Exception:
            self._contract_value_cache[product_id] = 1.0
            return 1.0

    async def _resolve_tick_size(self, product_id: int, symbol: str) -> float:
        if product_id in self._tick_size_cache:
            return self._tick_size_cache[product_id]
        cfg = self.config.get("trading", {}).get("tick_size_by_symbol") or {}
        if symbol in cfg:
            t = float(cfg[symbol])
            self._tick_size_cache[product_id] = t
            return t
        try:
            prod = await self.client.get_product(symbol)
            if isinstance(prod, list) and prod:
                prod = prod[0]
            if not isinstance(prod, dict):
                self._tick_size_cache[product_id] = 0.5
                return 0.5
            t = float(prod.get("tick_size", 0.5))
            self._tick_size_cache[product_id] = t
            return t
        except Exception:
            self._tick_size_cache[product_id] = 0.5
            return 0.5

    async def _read_exchange_position_size(self, product_id: int) -> int:
        raw = await self.client.get_position(product_id)
        if raw is None:
            return 0
        if isinstance(raw, dict):
            return int(float(raw.get("size", 0)))
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            return int(float(raw[0].get("size", 0)))
        return 0

    async def load_exchange_positions(
        self,
        price_by_symbol: dict[str, float],
    ) -> ExchangePositionOverview:
        """Open positions from Delta (GET /v2/positions/margined), independent of bot state."""
        if self.paper_trading:
            return ExchangePositionOverview(source="paper")
        product_map: dict[int, str] = {}
        raw_ids = self.config.get("trading", {}).get("product_ids", {})
        if isinstance(raw_ids, dict):
            for sym, pid in raw_ids.items():
                try:
                    product_map[int(pid)] = str(sym)
                except (TypeError, ValueError):
                    continue
        try:
            raw = await self.client.get_margined_positions()
        except CriticalBotError as exc:
            return ExchangePositionOverview(source="error", error=str(exc))
        except Exception as exc:
            return ExchangePositionOverview(source="error", error=str(exc)[:200])
        cv_map: dict[int, float] = {}
        cfg_cv = self.config.get("trading", {}).get("contract_value_by_symbol") or {}
        for pid_i, sym in product_map.items():
            if sym in cfg_cv:
                cv_map[pid_i] = float(cfg_cv[sym])
        for pid in open_position_product_ids(raw):
            if pid not in cv_map:
                sym = product_map.get(pid, "")
                if sym:
                    cv_map[pid] = await self._resolve_contract_value(pid, sym)
                else:
                    cv_map[pid] = 1.0
        return margined_positions_to_overview(
            raw,
            price_by_symbol,
            product_id_to_symbol=product_map or None,
            product_id_to_contract_value=cv_map or None,
        )

    @property
    def paper_trading(self) -> bool:
        return bool(self.config["trading"].get("paper_trading", True))

    async def open_position(self, symbol: str, side: str, price: float) -> PositionState:
        existing = self.position_for(symbol)
        if existing.active:
            raise CriticalBotError(f"Order attempted while {symbol} position is already active")

        max_open = int(self.config["risk_management"].get("max_open_positions", 1))
        if self.active_position_count >= max_open:
            raise CriticalBotError(
                f"Max open positions reached ({self.active_position_count}/{max_open})"
            )

        inst = instrument_settings(self.config, symbol)
        risk = self.config["risk_management"]
        product_id = inst.product_id
        quantity = inst.quantity
        order_type = str(self.config["trading"]["order_type"])

        tp_pct = inst.take_profit_percent
        sl_pct = inst.stop_loss_percent
        stop_loss_ratio = _percent_to_ratio(sl_pct)
        take_profit_ratio = _percent_to_ratio(tp_pct)
        trailing_stop = risk.get("trailing_stop", {})
        trailing_ratio = _percent_to_ratio(float(trailing_stop.get("trail_percent", 0.0)))
        trailing_enabled = bool(trailing_stop.get("enabled", False)) and trailing_ratio > 0
        if side == "buy":
            stop_loss = price * (1 - stop_loss_ratio)
            take_profit = price * (1 + take_profit_ratio)
        else:
            stop_loss = price * (1 + stop_loss_ratio)
            take_profit = price * (1 - take_profit_ratio)

        tick = await self._resolve_tick_size(product_id, symbol)
        stop_loss = _round_to_tick(stop_loss, tick)
        take_profit = _round_to_tick(take_profit, tick)

        attach_bracket = bool(risk.get("exchange_bracket_orders", risk.get("enable_bracket_tp_sl", True))) and not self.paper_trading
        trigger_method = str(risk.get("bracket_stop_trigger_method", "mark_price"))

        take_profit_limit: float | None = None
        stop_loss_limit: float | None = None
        if attach_bracket:
            if tp_pct <= 0 or sl_pct <= 0:
                self.logger.error("[ERROR] Invalid TP/SL calculation | take_profit_percent and stop_loss_percent must be > 0")
                raise CriticalBotError("Bracket TP/SL requires positive take_profit_percent and stop_loss_percent")
            tp_buf = float(risk.get("tp_limit_buffer_percent", 0.1))
            sl_buf = float(risk.get("sl_limit_buffer_percent", 0.1))
            tp_lim, sl_lim = compute_bracket_limit_prices(side, stop_loss, take_profit, tp_buf, sl_buf)
            take_profit_limit = _round_to_tick(tp_lim, tick)
            stop_loss_limit = _round_to_tick(sl_lim, tick)
            v_err = validate_bracket_prices(
                side, price, stop_loss, take_profit, stop_loss_limit, take_profit_limit
            )
            if v_err:
                self.logger.error("[ERROR] Invalid TP/SL calculation | %s", v_err)
                raise CriticalBotError(f"Invalid TP/SL: {v_err}")
            self.logger.info(
                "===============================\n"
                "ENTRY PRICE : %.8f\n"
                "ORDER SIDE  : %s\n"
                "TP %%        : %s%%\n"
                "SL %%        : %s%%\n"
                "TP PRICE    : %.8f\n"
                "SL PRICE    : %.8f\n"
                "TP LIMIT    : %.8f\n"
                "SL LIMIT    : %.8f\n"
                "===============================",
                price,
                side.upper(),
                tp_pct,
                sl_pct,
                take_profit,
                stop_loss,
                take_profit_limit,
                stop_loss_limit,
            )

        brackets_on = await self._place_entry_order(
            product_id,
            quantity,
            side,
            order_type,
            price,
            symbol,
            stop_loss,
            take_profit,
            trigger_method,
            attach_bracket,
            take_profit_limit=take_profit_limit,
            stop_loss_limit=stop_loss_limit,
        )

        contract_value = await self._resolve_contract_value(product_id, symbol)

        self.positions[symbol] = PositionState(
            symbol=symbol,
            active=True,
            side=side,
            entry_price=price,
            quantity=quantity,
            contract_value=contract_value,
            stop_loss=stop_loss,
            take_profit=take_profit,
            exchange_brackets=brackets_on,
            trailing_stop_active=trailing_enabled and not brackets_on,
            trailing_stop_percent=float(trailing_stop.get("trail_percent", 0.0)),
            trailing_reference_price=price,
        )
        self.tracker.append(
            TradeRecord(
                timestamp=format_ist(),
                trade_date=today_ist(),
                symbol=symbol,
                side=side,
                quantity=quantity,
                entry_price=price,
                exit_price=0.0,
                realized_pnl=0.0,
                status="OPEN",
                reason="signal",
                paper_trading=self.paper_trading,
            )
        )
        self.logger.info(
            "%s POSITION OPENED | SYMBOL=%s | ENTRY=%.2f | SL=%.2f | TP=%.2f | EXCHANGE_BRACKET=%s",
            side.upper(),
            symbol,
            price,
            stop_loss,
            take_profit,
            brackets_on,
        )
        return self.positions[symbol]

    async def validate_exit(self, symbol: str, current_price: float) -> PositionState:
        position = self.position_for(symbol)
        if not position.active:
            return position

        position.unrealized_pnl = self._calculate_pnl(position, current_price)
        product_id = int(self.config["trading"]["product_ids"][symbol])

        if position.exchange_brackets:
            try:
                size = await self._read_exchange_position_size(product_id)
            except Exception as exc:
                self.logger.warning("Exchange position sync failed: %s", exc)
                size = None
            if size is not None and size == 0:
                await self.close_position(symbol, current_price, "exchange_bracket", place_exit_order=False)
                return self.position_for(symbol)
            return position

        self._update_trailing_stop(position, current_price)
        exit_reason = ""
        if position.side == "buy":
            if current_price <= position.stop_loss:
                exit_reason = "stop_loss"
            elif current_price >= position.take_profit:
                exit_reason = "take_profit"
        else:
            if current_price >= position.stop_loss:
                exit_reason = "stop_loss"
            elif current_price <= position.take_profit:
                exit_reason = "take_profit"

        if exit_reason:
            await self.close_position(symbol, current_price, exit_reason)
        return self.position_for(symbol)

    async def close_position(self, symbol: str, price: float, reason: str, *, place_exit_order: bool = True) -> PositionState:
        position = self.position_for(symbol)
        if not position.active:
            return position
        exit_side = "sell" if position.side == "buy" else "buy"
        product_id = int(self.config["trading"]["product_ids"][symbol])
        if place_exit_order:
            await self._place_exit_order(product_id, position.quantity, exit_side, price)
        else:
            self.logger.info("POSITION CLOSED (sync, no exit order) | SYMBOL=%s | REASON=%s", symbol, reason)
        realized_pnl = self._calculate_pnl(position, price)
        self.tracker.append(
            TradeRecord(
                timestamp=format_ist(),
                trade_date=today_ist(),
                symbol=symbol,
                side=position.side,
                quantity=position.quantity,
                entry_price=position.entry_price,
                exit_price=price,
                realized_pnl=realized_pnl,
                status="CLOSED",
                reason=reason,
                paper_trading=self.paper_trading,
            )
        )
        self.logger.info("POSITION CLOSED | SYMBOL=%s | REASON=%s | PNL=%.2f", symbol, reason, realized_pnl)
        del self.positions[symbol]
        return PositionState(symbol=symbol, realized_pnl=realized_pnl)

    def _calculate_pnl(self, position: PositionState, current_price: float) -> float:
        if not position.active:
            return position.realized_pnl
        if position.side == "buy":
            return (current_price - position.entry_price) * position.quantity * position.contract_value
        return (position.entry_price - current_price) * position.quantity * position.contract_value

    def _update_trailing_stop(self, position: PositionState, current_price: float) -> None:
        if not position.trailing_stop_active or position.trailing_stop_percent <= 0:
            return
        trail_ratio = _percent_to_ratio(position.trailing_stop_percent)
        if position.side == "buy":
            best_price = max(position.trailing_reference_price, current_price)
            trailed_stop = best_price * (1 - trail_ratio)
            if trailed_stop > position.stop_loss:
                position.stop_loss = trailed_stop
                position.trailing_reference_price = best_price
                self.logger.info("TRAILING STOP UPDATED | SYMBOL=%s SIDE=BUY | SL=%.2f", position.symbol, position.stop_loss)
        else:
            best_price = min(position.trailing_reference_price, current_price)
            trailed_stop = best_price * (1 + trail_ratio)
            if trailed_stop < position.stop_loss:
                position.stop_loss = trailed_stop
                position.trailing_reference_price = best_price
                self.logger.info("TRAILING STOP UPDATED | SYMBOL=%s SIDE=SELL | SL=%.2f", position.symbol, position.stop_loss)

    async def _place_entry_order(
        self,
        product_id: int,
        quantity: float,
        side: str,
        order_type: str,
        price: float,
        symbol: str,
        stop_loss: float,
        take_profit: float,
        trigger_method: str,
        attach_bracket: bool,
        take_profit_limit: float | None = None,
        stop_loss_limit: float | None = None,
    ) -> bool:
        """Place entry; optionally Delta bracket TP/SL. Returns True if exchange brackets are active."""
        if self.paper_trading:
            self.logger.info(
                "PAPER ORDER | PRODUCT=%s | SIDE=%s | QTY=%s | PRICE=%.2f | SL=%.2f | TP=%.2f | BRACKET=%s",
                product_id,
                side,
                quantity,
                price,
                stop_loss,
                take_profit,
                attach_bracket,
            )
            return False
        await self.client.set_leverage(product_id, self.config["trading"]["leverage"])
        sl_s = _price_to_api_str(stop_loss)
        tp_s = _price_to_api_str(take_profit)
        if not attach_bracket:
            await self.client.place_order(product_id, quantity, side, order_type)
            return False

        if take_profit_limit is None or stop_loss_limit is None:
            self.logger.error("[ERROR] Invalid TP/SL calculation | missing limit legs for bracket order")
            raise CriticalBotError("Bracket order requires computed TP/SL limit prices")

        effective_type = "market_order"
        if order_type != "market_order":
            self.logger.warning(
                "Bracket entry requires market_order; overriding trading.order_type=%s",
                order_type,
            )
        sl_lim_s = _price_to_api_str(stop_loss_limit)
        tp_lim_s = _price_to_api_str(take_profit_limit)

        try:
            await self.client.place_order(
                product_id,
                quantity,
                side,
                effective_type,
                product_symbol=symbol,
                use_product_symbol_only=True,
                bracket_stop_loss_price=sl_s,
                bracket_take_profit_price=tp_s,
                bracket_stop_loss_limit_price=sl_lim_s,
                bracket_take_profit_limit_price=tp_lim_s,
                bracket_stop_trigger_method=trigger_method,
            )
            self.logger.info(
                "ENTRY+BRACKET | symbol=%s SL=%s TP=%s SL_LIM=%s TP_LIM=%s trigger=%s",
                symbol,
                sl_s,
                tp_s,
                sl_lim_s,
                tp_lim_s,
                trigger_method,
            )
            return True
        except DeltaAPIError as exc:
            self.logger.warning("Combined entry+bracket failed, trying market then attach: %s", exc)
            await self.client.place_order(product_id, quantity, side, effective_type)
            try:
                await self.client.place_bracket_on_position(
                    product_symbol=symbol,
                    stop_loss_order={
                        "order_type": "limit_order",
                        "stop_price": sl_s,
                        "limit_price": sl_lim_s,
                    },
                    take_profit_order={
                        "order_type": "limit_order",
                        "stop_price": tp_s,
                        "limit_price": tp_lim_s,
                    },
                    bracket_stop_trigger_method=trigger_method,
                )
                self.logger.info(
                    "BRACKET ATTACHED post-fill | SL=%s TP=%s SL_LIM=%s TP_LIM=%s",
                    sl_s,
                    tp_s,
                    sl_lim_s,
                    tp_lim_s,
                )
                return True
            except DeltaAPIError as exc2:
                self.logger.error(
                    "Bracket attach failed after market entry: %s — bot will monitor TP/SL in software only",
                    exc2,
                )
                return False

    async def _place_exit_order(self, product_id: int, quantity: float, side: str, price: float) -> None:
        if self.paper_trading:
            self.logger.info("PAPER EXIT | PRODUCT=%s | SIDE=%s | QTY=%s | PRICE=%.2f", product_id, side, quantity, price)
            return
        await self.client.place_order(product_id, quantity, side, "market_order", reduce_only=True)


def _percent_to_ratio(percent: float) -> float:
    if percent < 0:
        raise CriticalBotError("Risk percentage values must be zero or greater")
    return percent / 100
