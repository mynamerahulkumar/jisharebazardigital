import unittest

from broker.bracket_prices import compute_bracket_limit_prices, validate_bracket_prices


class BracketPricesTest(unittest.TestCase):
    def test_buy_limits_below_triggers_and_doc_pattern(self) -> None:
        entry = 100_000.0
        sl_trigger = 97_000.0
        tp_trigger = 105_000.0
        tp_lim, sl_lim = compute_bracket_limit_prices(
            "buy", sl_trigger, tp_trigger, tp_limit_buffer_percent=0.1, sl_limit_buffer_percent=0.1
        )
        self.assertAlmostEqual(tp_lim, 104_895.0, places=6)
        self.assertAlmostEqual(sl_lim, 96_903.0, places=6)
        self.assertLess(tp_lim, tp_trigger)
        self.assertLess(sl_lim, sl_trigger)
        self.assertGreater(tp_trigger, entry)
        self.assertLess(sl_trigger, entry)
        err = validate_bracket_prices(
            "buy", entry, sl_trigger, tp_trigger, sl_lim, tp_lim
        )
        self.assertIsNone(err)

    def test_sell_limits_above_triggers(self) -> None:
        entry = 100_000.0
        sl_trigger = 103_000.0
        tp_trigger = 95_000.0
        tp_lim, sl_lim = compute_bracket_limit_prices(
            "sell", sl_trigger, tp_trigger, tp_limit_buffer_percent=0.1, sl_limit_buffer_percent=0.1
        )
        self.assertGreater(tp_lim, tp_trigger)
        self.assertGreater(sl_lim, sl_trigger)
        self.assertLess(tp_trigger, entry)
        self.assertGreater(sl_trigger, entry)
        err = validate_bracket_prices(
            "sell", entry, sl_trigger, tp_trigger, sl_lim, tp_lim
        )
        self.assertIsNone(err)

    def test_validate_buy_rejects_bad_tp_sl(self) -> None:
        entry = 100_000.0
        err = validate_bracket_prices(
            "buy",
            entry,
            stop_loss=101_000.0,
            take_profit=99_000.0,
            stop_loss_limit=100_900.0,
            take_profit_limit=98_900.0,
        )
        self.assertIsNotNone(err)
        self.assertIn("BUY", err)


if __name__ == "__main__":
    unittest.main()
