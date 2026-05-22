from __future__ import annotations

from utils.helpers import CriticalBotError, PositionState
from utils.trade_tracker import TradeTracker


class RiskManager:
    def __init__(self, config: dict, tracker: TradeTracker) -> None:
        self.config = config
        self.tracker = tracker

    def max_trades_per_day(self) -> int:
        return int(self.config["risk_management"]["max_trades_per_day"])

    def can_open_new_trade(self) -> bool:
        """Whether another entry is allowed today (enforced before every new open)."""
        return self.tracker.entries_used_today() < self.max_trades_per_day()

    def validate_daily_limits(self, position_active: bool = False) -> None:
        """Stop the bot when at the daily entry limit and no positions left to manage."""
        risk = self.config["risk_management"]
        entries_used = self.tracker.entries_used_today()
        max_trades = self.max_trades_per_day()
        if entries_used >= max_trades and not position_active:
            open_rows = self.tracker.count_today()
            raise CriticalBotError(
                f"DAILY TRADE LIMIT REACHED | Entries used today: {entries_used}/{max_trades} "
                f"(open rows: {open_rows}, closed: {self.tracker.closed_count_today()})"
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
        return self.tracker.entries_used_today()

    def daily_pnl(self) -> float:
        return self.tracker.daily_realized_pnl()
