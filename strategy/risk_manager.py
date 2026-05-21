from __future__ import annotations

from utils.helpers import CriticalBotError, PositionState
from utils.trade_tracker import TradeTracker


class RiskManager:
    def __init__(self, config: dict, tracker: TradeTracker) -> None:
        self.config = config
        self.tracker = tracker

    def validate_daily_limits(self, position_active: bool = False) -> None:
        risk = self.config["risk_management"]
        trades_today = self.tracker.count_today()
        max_trades = int(risk["max_trades_per_day"])
        if trades_today >= max_trades and not position_active:
            raise CriticalBotError(
                f"DAILY TRADE LIMIT REACHED | Total trades today: {trades_today}/{max_trades}"
            )
        daily_pnl = self.tracker.daily_realized_pnl()
        loss_limit = float(risk.get("daily_loss_limit", 0))
        if loss_limit > 0 and daily_pnl <= -abs(loss_limit):
            raise CriticalBotError(f"DAILY LOSS LIMIT REACHED | Daily PnL: {daily_pnl:.2f}")

    def validate_open_position_limit(self, active_position_count: int) -> bool:
        max_open = int(self.config["risk_management"].get("max_open_positions", 1))
        return active_position_count < max_open

    def closed_trades_today(self) -> int:
        return self.tracker.closed_count_today()

    def trades_today(self) -> int:
        return self.tracker.count_today()

    def daily_pnl(self) -> float:
        return self.tracker.daily_realized_pnl()
