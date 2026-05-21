import unittest

from strategy.bollinger_strategy import BollingerReversalStrategy
from utils.helpers import Candle, IndicatorSnapshot


def _config() -> dict:
    return {
        "signal_control": {
            "enable_buy_signals": True,
            "enable_sell_signals": True,
        },
        "signal_engine": {
            "candle_confirmation_enabled": True,
        },
        "rsi": {
            "rsi_enabled": True,
            "rsi_buy_level": 30,
            "rsi_sell_level": 70,
        },
        "bollinger_bands": {
            "bb_enabled": True,
            "band_proximity_points": 0,
            "band_touch_offset_lower_points": 0,
            "band_touch_offset_upper_points": 0,
            "band_touch_include_forming_candle": False,
            "buy_breakout_include_forming": False,
            "sell_breakout_include_forming": False,
            "buy_breakout_use_live_price": False,
            "sell_breakout_use_live_price": False,
        },
    }


class BollingerReversalStrategyTest(unittest.TestCase):
    def test_buy_confirms_when_rsi_is_in_neutral_zone(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=105, low=94, close=98),
            Candle(timestamp=2, open=99, high=108, low=98, close=107),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=50)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "BUY_CONFIRMED")
        self.assertEqual(decision.action, "buy")
        self.assertTrue(decision.rsi_valid)

    def test_sell_confirms_when_rsi_is_in_neutral_zone(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=106, low=95, close=102),
            Candle(timestamp=2, open=101, high=102, low=90, close=94),
        ]
        indicators = IndicatorSnapshot(upper_band=105, lower_band=50, current_rsi=50)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "SELL_CONFIRMED")
        self.assertEqual(decision.action, "sell")
        self.assertTrue(decision.rsi_valid)

    def test_buy_confirms_when_rsi_oversold(self) -> None:
        """Longs from lower BB may sit in oversold RSI; buys only block when RSI is above sell level."""
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=105, low=94, close=98),
            Candle(timestamp=2, open=99, high=108, low=98, close=107),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=25)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "BUY_CONFIRMED")
        self.assertEqual(decision.action, "buy")
        self.assertTrue(decision.rsi_valid)

    def test_buy_rejects_when_rsi_overbought(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=105, low=94, close=98),
            Candle(timestamp=2, open=99, high=108, low=98, close=107),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=75)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "SIGNAL_REJECTED")
        self.assertEqual(decision.action, "hold")
        self.assertFalse(decision.rsi_valid)
        self.assertIn("RSI condition failed", decision.rejected_reason)

    def test_buy_wick_breakout_without_close_above_previous_high(self) -> None:
        """High clears prior bar's high even if close does not (wick breakout)."""
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=100, low=94, close=96),
            Candle(timestamp=2, open=97, high=101, low=96, close=99),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=45)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "BUY_CONFIRMED")
        self.assertEqual(decision.action, "buy")
        self.assertEqual(decision.rejected_reason, "")

    def test_sell_rejects_when_rsi_oversold(self) -> None:
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=106, low=95, close=102),
            Candle(timestamp=2, open=101, high=102, low=90, close=94),
        ]
        indicators = IndicatorSnapshot(upper_band=105, lower_band=50, current_rsi=25)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "SIGNAL_REJECTED")
        self.assertIn("RSI condition failed", decision.rejected_reason)

    def test_buy_confirms_near_lower_band_without_strict_touch(self) -> None:
        """Within band_proximity_points of lower band but min(low) > lower_band."""
        cfg = _config()
        cfg["bollinger_bands"]["band_proximity_points"] = 150
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100_200, high=100_180, low=100_100, close=100_150),
            Candle(timestamp=2, open=100_150, high=100_200, low=100_120, close=100_190),
        ]
        indicators = IndicatorSnapshot(upper_band=101_000, lower_band=100_000, current_rsi=50)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "BUY_CONFIRMED")
        self.assertEqual(decision.action, "buy")
        self.assertTrue(decision.lower_band_touched)

    def test_sell_confirms_near_upper_band_without_strict_touch(self) -> None:
        """Within band_proximity_points of upper band but max(high) < upper_band."""
        cfg = _config()
        cfg["bollinger_bands"]["band_proximity_points"] = 150
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100_000, high=99_900, low=99_800, close=99_900),
            Candle(timestamp=2, open=99_900, high=99_950, low=99_750, close=99_800),
        ]
        indicators = IndicatorSnapshot(upper_band=100_000, lower_band=98_000, current_rsi=50)

        decision = strategy.evaluate(candles, indicators)

        self.assertEqual(decision.status, "SELL_CONFIRMED")
        self.assertEqual(decision.action, "sell")
        self.assertTrue(decision.upper_band_touched)

    def test_offset_lower_aligns_higher_chart_band(self) -> None:
        """Raise effective lower by offset so min(low) near chart line counts without large proximity."""
        cfg = _config()
        cfg["bollinger_bands"]["band_proximity_points"] = 0
        cfg["bollinger_bands"]["band_touch_offset_lower_points"] = 5
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100_200, high=100_180, low=100_150, close=100_160),
            Candle(timestamp=2, open=100_160, high=100_200, low=100_142, close=100_150),
        ]
        indicators = IndicatorSnapshot(upper_band=101_000, lower_band=100_138, current_rsi=50)

        decision = strategy.evaluate(candles, indicators, None)

        self.assertTrue(decision.lower_band_touched)
        self.assertAlmostEqual(decision.band_touch_lower_line, 100_143, places=2)

    def test_forming_candle_low_arms_lower_proximity(self) -> None:
        """Completed bars stay above zone; live bar wick reaches effective lower."""
        cfg = _config()
        cfg["bollinger_bands"]["band_proximity_points"] = 0
        cfg["bollinger_bands"]["band_touch_offset_lower_points"] = 5
        cfg["bollinger_bands"]["band_touch_include_forming_candle"] = True
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100_200, high=100_180, low=100_160, close=100_170),
            Candle(timestamp=2, open=100_170, high=100_200, low=100_150, close=100_180),
        ]
        forming = Candle(timestamp=3, open=100_180, high=100_190, low=100_142, close=100_185)
        indicators = IndicatorSnapshot(upper_band=101_000, lower_band=100_138, current_rsi=50)

        decision_no = strategy.evaluate(candles, indicators, None)
        self.assertFalse(decision_no.lower_band_touched)

        decision_yes = strategy.evaluate(candles, indicators, forming)
        self.assertTrue(decision_yes.lower_band_touched)
        self.assertTrue(decision_yes.band_touch_includes_forming)

    def test_buy_breakout_equal_previous_high_counts(self) -> None:
        """max(high) == previous.high satisfies breakout (>=), not strict >."""
        strategy = BollingerReversalStrategy(_config())
        candles = [
            Candle(timestamp=1, open=100, high=100, low=94, close=96),
            Candle(timestamp=2, open=97, high=100, low=96, close=99),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=45)

        decision = strategy.evaluate(candles, indicators, None, None)

        self.assertTrue(decision.previous_high_broken)
        self.assertEqual(decision.status, "BUY_CONFIRMED")

    def test_buy_breakout_includes_forming_high(self) -> None:
        cfg = _config()
        cfg["bollinger_bands"]["buy_breakout_include_forming"] = True
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100, high=100, low=94, close=96),
            Candle(timestamp=2, open=97, high=99, low=96, close=99),
        ]
        forming = Candle(timestamp=3, open=99, high=101, low=98, close=100)
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=45)

        decision = strategy.evaluate(candles, indicators, forming, None)

        self.assertTrue(decision.previous_high_broken)
        self.assertEqual(decision.status, "BUY_CONFIRMED")

    def test_buy_breakout_live_price(self) -> None:
        cfg = _config()
        cfg["bollinger_bands"]["buy_breakout_use_live_price"] = True
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100, high=100, low=94, close=96),
            Candle(timestamp=2, open=97, high=99, low=96, close=99),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=45)

        decision = strategy.evaluate(candles, indicators, None, 101.0)

        self.assertTrue(decision.previous_high_broken)
        self.assertEqual(decision.status, "BUY_CONFIRMED")

    def test_require_bullish_false_allows_bearish_completed_bar(self) -> None:
        cfg = _config()
        cfg["bollinger_bands"]["require_bullish_candle_for_buy"] = False
        strategy = BollingerReversalStrategy(cfg)
        candles = [
            Candle(timestamp=1, open=100, high=100, low=94, close=96),
            Candle(timestamp=2, open=99, high=101, low=98, close=97),
        ]
        indicators = IndicatorSnapshot(upper_band=200, lower_band=95, current_rsi=45)

        decision = strategy.evaluate(candles, indicators, None, None)

        self.assertFalse(decision.bullish_candle)
        self.assertEqual(decision.status, "BUY_CONFIRMED")


if __name__ == "__main__":
    unittest.main()
