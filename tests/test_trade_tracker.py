from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils.trade_tracker import TradeRecord, TradeTracker
from utils.timezone_helper import today_ist


class TestTradeTrackerDailyLimit(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trades.csv"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _tracker(self) -> TradeTracker:
        with patch("utils.trade_tracker.today_ist", return_value="2026-05-21"):
            return TradeTracker(self.path)

    @patch("utils.trade_tracker.today_ist", return_value="2026-05-21")
    def test_close_updates_open_row_instead_of_duplicating(self, _today: object) -> None:
        tracker = TradeTracker(self.path)
        tracker.append(
            TradeRecord(
                timestamp="2026-05-21 10:00:00",
                trade_date="2026-05-21",
                symbol="BTCUSD",
                side="buy",
                quantity=1.0,
                entry_price=100.0,
                exit_price=0.0,
                realized_pnl=0.0,
                status="OPEN",
                reason="signal",
                paper_trading=False,
            )
        )
        tracker.close_open_row(
            "BTCUSD",
            exit_price=110.0,
            realized_pnl=10.0,
            reason="take_profit",
            paper_trading=False,
            closed_at="2026-05-21 11:00:00",
        )
        rows = list(tracker.rows())
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "CLOSED")
        self.assertEqual(rows[0]["exit_price"], "110.0")
        self.assertEqual(tracker.entries_used_today(), 1)
        self.assertEqual(tracker.count_today(), 0)

    @patch("utils.trade_tracker.today_ist", return_value="2026-05-21")
    def test_entries_used_counts_open_and_closed(self, _today: object) -> None:
        tracker = TradeTracker(self.path)
        for status in ("OPEN", "CLOSED", "OPEN"):
            tracker.append(
                TradeRecord(
                    timestamp="t",
                    trade_date="2026-05-21",
                    symbol="ETHUSD",
                    side="buy",
                    quantity=1.0,
                    entry_price=1.0,
                    exit_price=0.0,
                    realized_pnl=0.0,
                    status=status,
                    reason="signal",
                    paper_trading=True,
                )
            )
        self.assertEqual(tracker.entries_used_today(), 3)

    @patch("utils.trade_tracker.today_ist", return_value="2026-05-21")
    def test_reconcile_collapses_duplicate_open_rows(self, _today: object) -> None:
        with self.path.open("w", newline="", encoding="utf-8") as handle:
            handle.write(
                "timestamp,trade_date,symbol,side,quantity,entry_price,exit_price,"
                "realized_pnl,status,reason,paper_trading\n"
            )
            for i in range(10):
                handle.write(
                    f"2026-05-21 10:00:{i:02d},2026-05-21,BTCUSD,buy,1,100,0,0,OPEN,signal,False\n"
                )
        tracker = TradeTracker(self.path)
        self.assertEqual(tracker.count_today(), 1)
        self.assertEqual(tracker.entries_used_today(), 1)
        orphan_rows = [r for r in tracker.rows() if r.get("status") == "ORPHAN"]
        self.assertEqual(len(orphan_rows), 9)


if __name__ == "__main__":
    unittest.main()
