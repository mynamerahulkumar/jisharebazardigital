from __future__ import annotations

import math

from utils.helpers import Candle, IndicatorSnapshot


class IndicatorEngine:
    def __init__(self, bb_length: int, bb_std_dev: float, rsi_length: int) -> None:
        self.bb_length = bb_length
        self.bb_std_dev = bb_std_dev
        self.rsi_length = rsi_length

    def calculate(self, candles: list[Candle]) -> IndicatorSnapshot:
        if not candles:
            return IndicatorSnapshot()
        closes = [candle.close for candle in candles]
        upper, middle, lower = self._bollinger(closes)
        current_rsi = self._rsi(closes)
        previous_rsi = self._rsi(closes[:-1]) if len(closes) > self.rsi_length + 1 else current_rsi
        trend = "flat"
        if current_rsi > previous_rsi:
            trend = "up"
        elif current_rsi < previous_rsi:
            trend = "down"
        price = closes[-1]
        return IndicatorSnapshot(
            upper_band=upper,
            middle_band=middle,
            lower_band=lower,
            current_rsi=current_rsi,
            previous_rsi=previous_rsi,
            rsi_trend=trend,
            distance_upper=upper - price,
            distance_middle=price - middle,
            distance_lower=price - lower,
        )

    def _bollinger(self, closes: list[float]) -> tuple[float, float, float]:
        if len(closes) < self.bb_length:
            value = closes[-1]
            return value, value, value
        window = closes[-self.bb_length :]
        middle = sum(window) / len(window)
        variance = sum((price - middle) ** 2 for price in window) / len(window)
        std_dev = math.sqrt(variance)
        return middle + self.bb_std_dev * std_dev, middle, middle - self.bb_std_dev * std_dev

    def _rsi(self, closes: list[float]) -> float:
        if len(closes) <= self.rsi_length:
            return 50.0
        deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
        seed = deltas[: self.rsi_length]
        avg_gain = sum(delta for delta in seed if delta > 0) / self.rsi_length
        avg_loss = sum(-delta for delta in seed if delta < 0) / self.rsi_length

        for delta in deltas[self.rsi_length :]:
            gain = max(delta, 0)
            loss = max(-delta, 0)
            avg_gain = ((avg_gain * (self.rsi_length - 1)) + gain) / self.rsi_length
            avg_loss = ((avg_loss * (self.rsi_length - 1)) + loss) / self.rsi_length

        if avg_loss == 0:
            return 100.0 if avg_gain > 0 else 50.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
