import unittest

from broker.exchange_positions import margined_positions_to_overview, open_position_product_ids


class MarginedPositionsParseTest(unittest.TestCase):
    def test_counts_non_zero_sizes_and_sums_realized(self) -> None:
        raw = [
            {
                "product_id": 27,
                "product_symbol": "BTCUSD",
                "size": 1,
                "entry_price": "100",
                "realized_pnl": "-1.5",
            },
            {
                "product_id": 3136,
                "product_symbol": "ETHUSD",
                "size": -2,
                "entry_price": "200",
                "realized_pnl": "0.25",
            },
            {"product_id": 99, "product_symbol": "EMPTY", "size": 0, "entry_price": "1", "realized_pnl": "0"},
        ]
        prices = {"BTCUSD": 110.0, "ETHUSD": 195.0}
        cv = {27: 0.001, 3136: 0.001}
        ov = margined_positions_to_overview(
            raw,
            prices,
            product_id_to_symbol={27: "BTCUSD", 3136: "ETHUSD"},
            product_id_to_contract_value=cv,
        )
        self.assertEqual(ov.source, "ok")
        self.assertEqual(ov.open_count, 2)
        self.assertAlmostEqual(ov.sum_realized_pnl, -1.25)
        long_unreal = (110 - 100) * 1 * 0.001
        short_unreal = (200 - 195) * 2 * 0.001
        self.assertAlmostEqual(ov.sum_est_unrealized, long_unreal + short_unreal)

    def test_empty_list(self) -> None:
        ov = margined_positions_to_overview([], {}, product_id_to_symbol=None)
        self.assertEqual(ov.open_count, 0)

    def test_open_position_product_ids(self) -> None:
        raw = [{"product_id": 27, "size": 1}, {"product_id": 99, "size": 0}]
        self.assertEqual(open_position_product_ids(raw), {27})


if __name__ == "__main__":
    unittest.main()
