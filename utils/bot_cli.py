"""CLI helpers shared by run_bot_once.py, status.py, and stop.py."""

from __future__ import annotations

from typing import Any

from utils.helpers import active_trading_symbols, load_config, timeframe_summary


def resolve_trading_plan(config: dict[str, Any] | None = None) -> tuple[list[str], str]:
    """Enabled symbols and timeframe summary (same source as main.py TradingBot)."""
    cfg = config if config is not None else load_config()
    symbols = active_trading_symbols(cfg)
    if not symbols:
        raise ValueError("No enabled trading symbols in config (trading.instruments)")
    return symbols, timeframe_summary(cfg, symbols)


def format_trading_plan(symbols: list[str], summary: str, config: dict[str, Any] | None = None) -> str:
    cfg = config if config is not None else load_config()
    max_trades = int(cfg["risk_management"]["max_trades_per_day"])
    return (
        f"Trading plan: {len(symbols)} symbol(s) — {', '.join(symbols)} | {summary} | "
        f"max_trades_per_day={max_trades}"
    )


def format_daily_trade_usage(config: dict[str, Any] | None = None) -> str:
    """Entries used today vs config limit (same CSV as TradingBot / start.py)."""
    from utils.trade_tracker import TradeTracker

    cfg = config if config is not None else load_config()
    max_trades = int(cfg["risk_management"]["max_trades_per_day"])
    used = TradeTracker().entries_used_today()
    remaining = max(max_trades - used, 0)
    return f"Daily entries (logs/trades.csv): {used}/{max_trades} used, {remaining} remaining"
