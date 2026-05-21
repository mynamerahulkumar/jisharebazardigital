from __future__ import annotations

import os
import resource
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv

from utils.timezone_helper import now_ist

ROOT_DIR = Path(__file__).resolve().parents[1]


class BotShutdown(Exception):
    """Raised when the bot should stop gracefully."""


class CriticalBotError(BotShutdown):
    """Raised for critical failures where continuing would waste cost or risk money."""


def load_config(path: str | Path = "config/config.yaml") -> dict[str, Any]:
    load_dotenv()
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = ROOT_DIR / config_path
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}
    config = _expand_env(raw_config)
    normalize_trading_config(config)
    return config


def normalize_trading_config(config: dict[str, Any]) -> None:
    """Sync trading.symbols, product_ids, and contract_value_by_symbol from instruments."""
    trading = config.setdefault("trading", {})
    instruments = trading.get("instruments")
    if not isinstance(instruments, dict):
        return

    product_ids: dict[str, int] = {}
    contract_values: dict[str, float] = {}
    enabled_symbols: list[str] = []

    for symbol, meta in instruments.items():
        if not isinstance(meta, dict):
            continue
        pid = meta.get("product_id")
        if pid is not None:
            product_ids[str(symbol)] = int(pid)
        cv = meta.get("contract_value")
        if cv is not None:
            contract_values[str(symbol)] = float(cv)
        if meta.get("enabled", False):
            enabled_symbols.append(str(symbol))

    if product_ids:
        trading["product_ids"] = product_ids
    if contract_values:
        existing = trading.get("contract_value_by_symbol") or {}
        if isinstance(existing, dict):
            merged = {**existing, **contract_values}
        else:
            merged = contract_values
        trading["contract_value_by_symbol"] = merged
    if enabled_symbols:
        trading["symbols"] = enabled_symbols


@dataclass(frozen=True, slots=True)
class InstrumentSettings:
    symbol: str
    product_id: int
    contract_value: float
    quantity: float
    timeframe: str
    stop_loss_percent: float
    take_profit_percent: float


def instrument_settings(config: dict[str, Any], symbol: str) -> InstrumentSettings:
    """Per-symbol trading params with fallbacks to global trading / risk_management."""
    trading = config.get("trading", {})
    risk = config.get("risk_management", {})
    sym = str(symbol)

    meta: dict[str, Any] = {}
    instruments = trading.get("instruments")
    if isinstance(instruments, dict) and sym in instruments:
        raw = instruments[sym]
        if isinstance(raw, dict):
            meta = raw

    product_ids = trading.get("product_ids") or {}
    if sym not in product_ids and meta.get("product_id") is None:
        raise CriticalBotError(f"No product_id configured for {sym}")

    product_id = int(meta.get("product_id") or product_ids[sym])

    cv_map = trading.get("contract_value_by_symbol") or {}
    contract_value = float(
        meta.get("contract_value")
        or cv_map.get(sym)
        or 1.0
    )

    default_qty = float(trading.get("quantity", 1))
    default_tf = str(trading.get("timeframe", "5m"))
    default_sl = float(risk.get("stop_loss_percent", 0.2))
    default_tp = float(risk.get("take_profit_percent", 0.4))

    return InstrumentSettings(
        symbol=sym,
        product_id=product_id,
        contract_value=contract_value,
        quantity=float(meta.get("quantity", default_qty)),
        timeframe=str(meta.get("timeframe", default_tf)),
        stop_loss_percent=float(meta.get("stop_loss_percent", default_sl)),
        take_profit_percent=float(meta.get("take_profit_percent", default_tp)),
    )


def timeframe_summary(config: dict[str, Any], symbols: list[str] | None = None) -> str:
    """Compact timeframe label for CLI header, e.g. BTCUSD:5m | ETHUSD:15m."""
    syms = symbols or active_trading_symbols(config)
    parts = [f"{s}:{instrument_settings(config, s).timeframe}" for s in syms]
    return " | ".join(parts) if parts else "n/a"


def active_trading_symbols(config: dict[str, Any]) -> list[str]:
    trading = config.get("trading", {})
    instruments = trading.get("instruments")
    if isinstance(instruments, dict):
        return [
            str(symbol)
            for symbol, meta in instruments.items()
            if isinstance(meta, dict) and meta.get("enabled", False)
        ]
    symbols = trading.get("symbols")
    if isinstance(symbols, list) and symbols:
        return [str(s) for s in symbols]
    product_ids = trading.get("product_ids")
    if isinstance(product_ids, dict):
        return list(product_ids.keys())
    return []


def _expand_env(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        return os.getenv(value[2:-1], "")
    return value


def ensure_directories() -> None:
    for directory in ("logs", "config", "strategy", "broker", "ui", "utils"):
        (ROOT_DIR / directory).mkdir(exist_ok=True)


def timeframe_to_seconds(timeframe: str) -> int:
    normalized = timeframe.strip().lower()
    unit = normalized[-1]
    amount = int(normalized[:-1])
    if unit == "m":
        return amount * 60
    if unit == "h":
        return amount * 60 * 60
    if unit == "d":
        return amount * 24 * 60 * 60
    raise ValueError(f"Unsupported timeframe: {timeframe}")


def unix_seconds() -> int:
    return int(time.time())


def normalize_candle_timestamp(timestamp: int, timeframe: str) -> int:
    if timestamp > 10_000_000_000_000:
        timestamp = timestamp // 1_000_000
    elif timestamp > 10_000_000_000:
        timestamp = timestamp // 1_000
    candle_seconds = timeframe_to_seconds(timeframe)
    return timestamp - (timestamp % candle_seconds)


def system_usage() -> dict[str, float]:
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    memory_mb = max_rss / (1024 * 1024) if sys.platform == "darwin" else max_rss / 1024
    load_avg = os.getloadavg()[0] if hasattr(os, "getloadavg") else 0.0
    return {"memory_mb": round(memory_mb, 2), "cpu_load_1m": round(load_avg, 2)}


@dataclass(slots=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def direction(self) -> str:
        if self.close > self.open:
            return "bullish"
        if self.close < self.open:
            return "bearish"
        return "neutral"


@dataclass(slots=True)
class IndicatorSnapshot:
    upper_band: float = 0.0
    middle_band: float = 0.0
    lower_band: float = 0.0
    current_rsi: float = 0.0
    previous_rsi: float = 0.0
    rsi_trend: str = "flat"
    distance_upper: float = 0.0
    distance_middle: float = 0.0
    distance_lower: float = 0.0


@dataclass(slots=True)
class SignalDecision:
    action: Literal["buy", "sell", "hold"] = "hold"
    status: str = "WAITING"
    rejected_reason: str = ""
    upper_band_touched: bool = False
    lower_band_touched: bool = False
    bearish_candle: bool = False
    bullish_candle: bool = False
    previous_low_broken: bool = False
    previous_high_broken: bool = False
    rsi_valid: bool = False
    confirmation_active: bool = False
    # Band proximity diagnostics (filled by BollingerReversalStrategy when BB enabled)
    band_touch_min_low: float = 0.0
    band_touch_max_high: float = 0.0
    band_touch_lower_line: float = 0.0
    band_touch_upper_line: float = 0.0
    band_touch_lower_threshold: float = 0.0
    band_touch_upper_threshold: float = 0.0
    band_touch_includes_forming: bool = False

    @property
    def should_trade(self) -> bool:
        return self.action in {"buy", "sell"} and not self.rejected_reason


@dataclass(slots=True)
class PositionState:
    symbol: str = ""
    active: bool = False
    side: str = ""
    entry_price: float = 0.0
    quantity: float = 0.0
    # (mark - entry) * quantity * contract_value ≈ USD PnL for vanilla linear perps on Delta
    contract_value: float = 1.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    """True when SL/TP were sent to Delta (bracket); validate_exit syncs flat from exchange."""
    exchange_brackets: bool = False
    trailing_stop_active: bool = False
    trailing_stop_percent: float = 0.0
    trailing_reference_price: float = 0.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0

    @property
    def current_pnl(self) -> float:
        return self.realized_pnl + self.unrealized_pnl


@dataclass(slots=True)
class ExchangePositionOverview:
    """Open legs from Delta GET /v2/positions/margined; not the same as bot-managed PositionState."""

    source: Literal["off", "paper", "ok", "error"] = "off"
    error: str = ""
    open_count: int = 0
    position_lines: tuple[str, ...] = ()
    sum_realized_pnl: float = 0.0
    sum_est_unrealized: float = 0.0


@dataclass(slots=True)
class SymbolMonitorState:
    symbol: str
    timeframe: str
    current_price: float
    current_candle: Candle | None
    previous_candle: Candle | None
    indicators: IndicatorSnapshot
    signal: SignalDecision
    position: PositionState
    realized_pnl_today: float = 0.0
    forming_candle: Candle | None = None


@dataclass(slots=True)
class BotMonitorSnapshot:
    timeframe: str
    symbols: list[SymbolMonitorState]
    trades_today: int
    closed_trades_today: int
    max_trades_per_day: int
    daily_pnl: float
    daily_loss_limit: float
    total_unrealized_pnl: float
    total_realized_today: float
    overall_pnl: float
    api_status: str
    websocket_status: str
    last_signal_check: str
    next_signal_check_seconds: int
    running_seconds: int
    memory_mb: float
    cpu_load_1m: float
    exchange_positions: ExchangePositionOverview = field(default_factory=ExchangePositionOverview)
    created_at: str = field(default_factory=lambda: now_ist().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Legacy single-symbol snapshot (kept for compatibility if referenced elsewhere).
@dataclass(slots=True)
class MonitoringSnapshot:
    symbol: str
    timeframe: str
    current_price: float
    current_candle: Candle | None
    previous_candle: Candle | None
    indicators: IndicatorSnapshot
    signal: SignalDecision
    position: PositionState
    trades_today: int
    closed_trades_today: int
    max_trades_per_day: int
    daily_pnl: float
    daily_loss_limit: float
    api_status: str
    websocket_status: str
    last_signal_check: str
    next_signal_check_seconds: int
    running_seconds: int
    memory_mb: float
    cpu_load_1m: float
    forming_candle: Candle | None = None
    exchange_positions: ExchangePositionOverview = field(default_factory=ExchangePositionOverview)
    created_at: str = field(default_factory=lambda: now_ist().strftime("%Y-%m-%d %H:%M:%S"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
