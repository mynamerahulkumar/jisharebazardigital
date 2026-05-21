import unittest

from broker.delta_client import (
    delta_order_error_code,
    isolated_margin_rejection_hint,
    is_recoverable_entry_order_error,
)


class DeltaClientErrorsTest(unittest.TestCase):
    def test_insufficient_margin_recoverable(self) -> None:
        msg = (
            'Delta HTTP 400: {"error":{"code":"insufficient_margin","context":'
            '{"asset_symbol":"USD","available_balance":"77.81","margin_mode":"isolated",'
            '"required_additional_balance":"2.89"}},"success":false}'
        )
        self.assertTrue(is_recoverable_entry_order_error(msg))
        self.assertEqual(delta_order_error_code(msg), "insufficient_margin")
        hint = isolated_margin_rejection_hint(msg)
        self.assertIn("Isolated margin", hint)
        self.assertIn("2.89", hint)


if __name__ == "__main__":
    unittest.main()
