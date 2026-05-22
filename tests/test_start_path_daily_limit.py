from __future__ import annotations

import unittest
from unittest.mock import patch

from utils.bot_cli import format_daily_trade_usage, format_trading_plan, resolve_trading_plan
from utils.helpers import load_config


REPO_CONFIG = load_config()


class TestStartPathUsesConfigDailyLimit(unittest.TestCase):
    """start.py → main.main() reads the same config and CSV rules as run_bot_once.py."""

    def test_config_max_trades_per_day_is_seven(self) -> None:
        self.assertEqual(int(REPO_CONFIG["risk_management"]["max_trades_per_day"]), 7)

    def test_run_bot_once_banner_includes_limit(self) -> None:
        symbols, summary = resolve_trading_plan(REPO_CONFIG)
        plan = format_trading_plan(symbols, summary, REPO_CONFIG)
        self.assertIn("max_trades_per_day=7", plan)

    def test_daily_usage_line_mentions_csv(self) -> None:
        with patch("utils.trade_tracker.today_ist", return_value="2099-01-01"):
            usage = format_daily_trade_usage(REPO_CONFIG)
        self.assertIn("7", usage)
        self.assertIn("logs/trades.csv", usage)


if __name__ == "__main__":
    unittest.main()
