import unittest

from main import _completed_candles, _parse_candle
from strategy.indicator_engine import IndicatorEngine
from utils.helpers import Candle


class IndicatorEngineTest(unittest.TestCase):
    def test_rsi_uses_wilder_smoothing(self) -> None:
        closes = [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
            46.03,
            46.41,
            46.22,
            45.64,
            46.21,
        ]

        engine = IndicatorEngine(bb_length=20, bb_std_dev=2.0, rsi_length=14)

        self.assertAlmostEqual(engine._rsi(closes), 62.880718309962404)


class CandleHandlingTest(unittest.TestCase):
    def test_completed_candles_excludes_current_timeframe_bucket(self) -> None:
        candles = [
            Candle(timestamp=3_600, open=1, high=2, low=1, close=2),
            Candle(timestamp=7_200, open=2, high=3, low=2, close=3),
            Candle(timestamp=10_800, open=3, high=4, low=3, close=4),
        ]

        completed = _completed_candles(candles, "1h", now=10_900)

        self.assertEqual([candle.timestamp for candle in completed], [3_600, 7_200])

    def test_parse_candle_normalizes_rest_timestamp(self) -> None:
        candle = _parse_candle(
            {
                "time": 1_778_249_123_000,
                "open": "10",
                "high": "12",
                "low": "9",
                "close": "11",
                "volume": "100",
            },
            "1h",
        )

        self.assertEqual(candle.timestamp, 1_778_248_800)
        self.assertEqual(candle.close, 11.0)


if __name__ == "__main__":
    unittest.main()
