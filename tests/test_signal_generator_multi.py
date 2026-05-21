from __future__ import annotations

import time

from strategy.signal_generator import SignalGenerator
from utils.helpers import Candle, IndicatorSnapshot, PositionState


def _config() -> dict:
    return {
        "bollinger_bands": {"bb_length": 20, "bb_std_dev": 2.0},
        "rsi": {"rsi_length": 14},
        "signal_engine": {"cooldown_seconds": 300},
        "signal_control": {"enable_buy_signals": True, "enable_sell_signals": True},
    }


def _minimal_candles() -> list[Candle]:
    base = 1_700_000_000
    return [
        Candle(timestamp=base, open=100, high=101, low=99, close=100),
        Candle(timestamp=base + 300, open=100, high=102, low=98, close=101),
    ]


def test_cooldown_is_per_symbol() -> None:
    gen = SignalGenerator(_config())
    gen.mark_trade_executed("BTCUSD")
    gen._last_trade_at["ETHUSD"] = 0.0

    _, decision_eth = gen.evaluate(
        _minimal_candles(),
        PositionState(symbol="ETHUSD"),
    )
    assert decision_eth.status != "SIGNAL_REJECTED" or decision_eth.rejected_reason != "cooldown active"


def test_position_active_only_blocks_that_symbol() -> None:
    gen = SignalGenerator(_config())
    active = PositionState(symbol="BTCUSD", active=True, side="buy", entry_price=1.0, quantity=1.0)
    _, decision_btc = gen.evaluate(_minimal_candles(), active)
    assert decision_btc.status == "POSITION_ACTIVE"

    _, decision_eth = gen.evaluate(_minimal_candles(), PositionState(symbol="ETHUSD"))
    assert decision_eth.status != "POSITION_ACTIVE"
