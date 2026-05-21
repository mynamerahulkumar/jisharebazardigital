from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from utils.bot_cli import format_trading_plan, resolve_trading_plan
from utils.bot_process import REPO_ROOT, references_this_bot
from utils.helpers import load_config, normalize_trading_config


CONFIG_PATH = REPO_ROOT / "config" / "config.yaml"


class TestBotProcessDetection(unittest.TestCase):
    def test_references_start_py_in_repo(self) -> None:
        command = f"{REPO_ROOT}/.venv/bin/python -u {REPO_ROOT / 'start.py'}"
        self.assertTrue(references_this_bot(99999, command))

    def test_ignores_helper_scripts(self) -> None:
        for script in ("run_bot_once.py", "status.py", "stop.py"):
            command = f"{REPO_ROOT}/.venv/bin/python {REPO_ROOT / script}"
            self.assertFalse(references_this_bot(99999, command))

    def test_ignores_start_py_outside_repo_cwd(self) -> None:
        command = "python -u start.py"
        with patch("utils.bot_process.process_cwd", return_value=Path("/tmp")):
            self.assertFalse(references_this_bot(99999, command))


class TestBotCliTradingPlan(unittest.TestCase):
    def test_repo_config_three_symbols(self) -> None:
        config = load_config(CONFIG_PATH)
        symbols, summary = resolve_trading_plan(config)
        self.assertEqual(symbols, ["BTCUSD", "ETHUSD", "XAUTUSD"])
        text = format_trading_plan(symbols, summary)
        self.assertIn("3 symbol(s)", text)
        self.assertIn("XAUTUSD", text)

    def test_resolve_trading_plan_rejects_empty(self) -> None:
        config = {
            "trading": {
                "instruments": {
                    "BTCUSD": {"enabled": False, "product_id": 27},
                }
            }
        }
        normalize_trading_config(config)
        with self.assertRaises(ValueError):
            resolve_trading_plan(config)


if __name__ == "__main__":
    unittest.main()
