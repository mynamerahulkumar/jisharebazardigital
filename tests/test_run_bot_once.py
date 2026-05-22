from __future__ import annotations

import unittest
from pathlib import Path

from utils.bot_cli import resolve_trading_plan
from utils.helpers import active_trading_symbols, load_config, normalize_trading_config


REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


class TestRunBotOnceTradingPlan(unittest.TestCase):
    def test_repo_config_enabled_symbols_match_instruments(self) -> None:
        config = load_config(CONFIG_PATH)
        symbols = active_trading_symbols(config)
        self.assertGreaterEqual(len(symbols), 1)
        self.assertEqual(config["trading"]["symbols"], symbols)
        for sym in symbols:
            self.assertIn(sym, config["trading"]["product_ids"])
            self.assertIn(sym, config["trading"]["contract_value_by_symbol"])

    def test_resolve_trading_plan_matches_enabled_symbols(self) -> None:
        config = load_config(CONFIG_PATH)
        symbols, summary = resolve_trading_plan(config)
        self.assertEqual(symbols, active_trading_symbols(config))
        for sym in symbols:
            self.assertIn(f"{sym}:", summary)


if __name__ == "__main__":
    unittest.main()
