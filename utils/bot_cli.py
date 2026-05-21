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


def format_trading_plan(symbols: list[str], summary: str) -> str:
    return f"Trading plan: {len(symbols)} symbol(s) — {', '.join(symbols)} | {summary}"
