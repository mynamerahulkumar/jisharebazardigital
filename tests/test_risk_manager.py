from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from strategy.risk_manager import RiskManager
from utils.trade_tracker import TradeRecord, TradeTracker


class TestRiskManagerDailyLimit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trades.csv"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _manager(self, max_trades: int = 7, rows: list[TradeRecord] | None = None) -> RiskManager:
        config = {"risk_management": {"max_trades_per_day": max_trades, "daily_loss_limit": 0}}
        with patch("utils.trade_tracker.today_ist", return_value="2026-05-21"):
            tracker = TradeTracker(self.path)
            for record in rows or []:
                tracker.append(record)
            return RiskManager(config, tracker)

    @patch("utils.trade_tracker.today_ist", return_value="2026-05-21")
    def test_can_open_new_trade_respects_max_from_config(self, _today: object) -> None:
        rows = [
            TradeRecord(
                timestamp="t",
                trade_date="2026-05-21",
                symbol="BTCUSD",
                side="buy",
                quantity=1.0,
                entry_price=1.0,
                exit_price=0.0,
                realized_pnl=0.0,
                status="CLOSED",
                reason="signal",
                paper_trading=False,
            )
        ] * 7
        rm = self._manager(max_trades=7, rows=rows)
        self.assertEqual(rm.max_trades_per_day(), 7)
        self.assertFalse(rm.can_open_new_trade())

    @patch("utils.trade_tracker.today_ist", return_value="2026-05-21")
    def test_validate_daily_limits_allows_run_while_positions_open_at_limit(self, _today: object) -> None:
        rows = [
            TradeRecord(
                timestamp="t",
                trade_date="2026-05-21",
                symbol="BTCUSD",
                side="buy",
                quantity=1.0,
                entry_price=1.0,
                exit_price=0.0,
                realized_pnl=0.0,
                status="CLOSED",
                reason="signal",
                paper_trading=False,
            )
        ] * 7
        rm = self._manager(max_trades=7, rows=rows)
        rm.validate_daily_limits(position_active=True)

    @patch("utils.trade_tracker.today_ist", return_value="2026-05-21")
    def test_validate_daily_limits_stops_bot_when_at_limit_and_flat(self, _today: object) -> None:
        from utils.helpers import CriticalBotError

        rows = [
            TradeRecord(
                timestamp="t",
                trade_date="2026-05-21",
                symbol="BTCUSD",
                side="buy",
                quantity=1.0,
                entry_price=1.0,
                exit_price=0.0,
                realized_pnl=0.0,
                status="CLOSED",
                reason="signal",
                paper_trading=False,
            )
        ] * 7
        rm = self._manager(max_trades=7, rows=rows)
        with self.assertRaises(CriticalBotError):
            rm.validate_daily_limits(position_active=False)


if __name__ == "__main__":
    unittest.main()
