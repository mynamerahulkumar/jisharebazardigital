from __future__ import annotations

import unittest
from pathlib import Path

from utils.bot_cli import resolve_trading_plan
from utils.helpers import active_trading_symbols, load_config, normalize_trading_config


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


class TestRunBotOnceTradingPlan(unittest.TestCase):
    def test_repo_config_enables_all_three_coins(self) -> None:
        config = load_config(CONFIG_PATH)
        symbols = active_trading_symbols(config)
        self.assertEqual(symbols, ["BTCUSD", "ETHUSD", "XAUTUSD"])
        self.assertEqual(config["trading"]["symbols"], ["BTCUSD", "ETHUSD", "XAUTUSD"])
        for sym in symbols:
            self.assertIn(sym, config["trading"]["product_ids"])
            self.assertIn(sym, config["trading"]["contract_value_by_symbol"])

    def test_resolve_trading_plan_lists_all_three(self) -> None:
        config = load_config(CONFIG_PATH)
        symbols, summary = resolve_trading_plan(config)
        self.assertEqual(symbols, ["BTCUSD", "ETHUSD", "XAUTUSD"])
        self.assertIn("BTCUSD:5m", summary)
        self.assertIn("ETHUSD:5m", summary)
        self.assertIn("XAUTUSD:5m", summary)


if __name__ == "__main__":
    unittest.main()
