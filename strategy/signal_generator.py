from __future__ import annotations

import time

from strategy.bollinger_strategy import BollingerReversalStrategy
from strategy.indicator_engine import IndicatorEngine
from utils.helpers import Candle, IndicatorSnapshot, PositionState, SignalDecision


class SignalGenerator:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.indicators = IndicatorEngine(
            bb_length=int(config["bollinger_bands"]["bb_length"]),
            bb_std_dev=float(config["bollinger_bands"]["bb_std_dev"]),
            rsi_length=int(config["rsi"]["rsi_length"]),
        )
        self.strategy = BollingerReversalStrategy(config)
        self._last_trade_at: dict[str, float] = {}

    def evaluate(
        self,
        candles: list[Candle],
        position: PositionState,
        forming: Candle | None = None,
        live_price: float | None = None,
    ) -> tuple[IndicatorSnapshot, SignalDecision]:
        indicator_snapshot = self.indicators.calculate(candles)
        if position.active:
            return indicator_snapshot, SignalDecision(status="POSITION_ACTIVE", rejected_reason="active position exists")

        decision = self.strategy.evaluate(candles, indicator_snapshot, forming, live_price)
        cooldown = int(self.config["signal_engine"].get("cooldown_seconds", 0))
        symbol = position.symbol
        last_at = self._last_trade_at.get(symbol, 0.0)
        if decision.should_trade and cooldown > 0 and time.time() - last_at < cooldown:
            decision.action = "hold"
            decision.status = "SIGNAL_REJECTED"
            decision.rejected_reason = "cooldown active"
        return indicator_snapshot, decision

    def mark_trade_executed(self, symbol: str) -> None:
        self._last_trade_at[symbol] = time.time()
