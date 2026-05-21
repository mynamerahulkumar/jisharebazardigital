from __future__ import annotations

import unittest
from unittest.mock import AsyncMock, MagicMock

from broker.order_manager import OrderManager
from utils.helpers import CriticalBotError, PositionState


def _config(max_open: int = 5) -> dict:
    return {
        "trading": {
            "paper_trading": True,
            "product_ids": {"BTCUSD": 27, "ETHUSD": 3136},
            "contract_value_by_symbol": {"BTCUSD": 0.001, "ETHUSD": 0.01},
            "quantity": 1,
            "timeframe": "5m",
            "order_type": "market_order",
            "leverage": 10,
            "instruments": {
                "BTCUSD": {
                    "enabled": True,
                    "product_id": 27,
                    "contract_value": 0.001,
                    "quantity": 1,
                },
                "ETHUSD": {
                    "enabled": True,
                    "product_id": 3136,
                    "contract_value": 0.01,
                    "quantity": 5,
                    "stop_loss_percent": 0.25,
                    "take_profit_percent": 0.5,
                },
            },
        },
        "risk_management": {
            "stop_loss_percent": 0.2,
            "take_profit_percent": 0.4,
            "max_open_positions": max_open,
            "exchange_bracket_orders": False,
        },
    }


class OrderManagerMultiTest(unittest.IsolatedAsyncioTestCase):
    async def test_position_for_returns_inactive_by_default(self) -> None:
        om = OrderManager(_config(), AsyncMock(), MagicMock(), MagicMock())
        pos = om.position_for("BTCUSD")
        self.assertFalse(pos.active)
        self.assertEqual(pos.symbol, "BTCUSD")

    async def test_validate_exit_ignores_inactive_symbol(self) -> None:
        om = OrderManager(_config(), AsyncMock(), MagicMock(), MagicMock())
        om.positions["BTCUSD"] = PositionState(
            symbol="BTCUSD",
            active=True,
            side="buy",
            entry_price=100.0,
            quantity=1.0,
            contract_value=0.001,
            stop_loss=90.0,
            take_profit=110.0,
        )
        result = await om.validate_exit("ETHUSD", 50.0)
        self.assertFalse(result.active)
        self.assertTrue(om.positions["BTCUSD"].active)

    async def test_open_blocks_when_max_open_positions_reached(self) -> None:
        client = AsyncMock()
        om = OrderManager(_config(max_open=1), client, MagicMock(), MagicMock())
        om.positions["BTCUSD"] = PositionState(
            symbol="BTCUSD", active=True, side="buy", entry_price=1.0, quantity=1.0
        )
        with self.assertRaises(CriticalBotError):
            await om.open_position("ETHUSD", "buy", 2000.0)

    async def test_open_blocks_duplicate_symbol(self) -> None:
        client = AsyncMock()
        om = OrderManager(_config(), client, MagicMock(), MagicMock())
        om.positions["ETHUSD"] = PositionState(
            symbol="ETHUSD", active=True, side="sell", entry_price=1.0, quantity=1.0
        )
        with self.assertRaises(CriticalBotError):
            await om.open_position("ETHUSD", "buy", 2000.0)

    def test_active_position_count(self) -> None:
        om = OrderManager(_config(), AsyncMock(), MagicMock(), MagicMock())
        self.assertEqual(om.active_position_count, 0)
        om.positions["BTCUSD"] = PositionState(
            symbol="BTCUSD", active=True, side="buy", entry_price=1.0, quantity=1.0
        )
        om.positions["ETHUSD"] = PositionState(symbol="ETHUSD", active=False)
        self.assertEqual(om.active_position_count, 1)

    async def test_open_position_uses_per_symbol_quantity(self) -> None:
        client = AsyncMock()
        om = OrderManager(_config(), client, MagicMock(), MagicMock())
        await om.open_position("ETHUSD", "buy", 3000.0)
        pos = om.positions["ETHUSD"]
        self.assertEqual(pos.quantity, 5.0)


if __name__ == "__main__":
    unittest.main()
