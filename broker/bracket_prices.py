from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BracketTargets:
    """Delta bracket trigger and limit prices (rounded by caller)."""

    stop_loss: float
    take_profit: float
    stop_loss_limit: float
    take_profit_limit: float


def _ratio_from_config_percent(value: float) -> float:
    """Same convention as stop_loss_percent in config.yaml (e.g. 0.35 => 0.35%)."""
    return value / 100.0


def compute_bracket_limit_prices(
    side: str,
    stop_loss: float,
    take_profit: float,
    tp_limit_buffer_percent: float,
    sl_limit_buffer_percent: float,
) -> tuple[float, float]:
    """
    Derive limit exit prices from triggers (per bkp/tp_sl_delta.md).
    Long: TP/SL limits slightly below triggers. Short: limits slightly above.
    """
    tpr = _ratio_from_config_percent(tp_limit_buffer_percent)
    slr = _ratio_from_config_percent(sl_limit_buffer_percent)
    if side == "buy":
        take_profit_limit = take_profit * (1 - tpr)
        stop_loss_limit = stop_loss * (1 - slr)
    else:
        take_profit_limit = take_profit * (1 + tpr)
        stop_loss_limit = stop_loss * (1 + slr)
    return take_profit_limit, stop_loss_limit


def validate_bracket_prices(
    side: str,
    entry: float,
    stop_loss: float,
    take_profit: float,
    stop_loss_limit: float,
    take_profit_limit: float,
) -> str | None:
    """Return error message if invalid, else None."""
    if side == "buy":
        if not (take_profit > entry and stop_loss < entry):
            return "BUY requires TP above entry and SL below entry"
        if not (take_profit_limit < take_profit):
            return "BUY requires TP limit below TP trigger"
        if not (stop_loss_limit < stop_loss):
            return "BUY requires SL limit below SL trigger"
    else:
        if not (take_profit < entry and stop_loss > entry):
            return "SELL requires TP below entry and SL above entry"
        if not (take_profit_limit > take_profit):
            return "SELL requires TP limit above TP trigger"
        if not (stop_loss_limit > stop_loss):
            return "SELL requires SL limit above SL trigger"
    return None
