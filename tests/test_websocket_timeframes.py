from __future__ import annotations

import unittest

from broker.websocket_client import DeltaWebSocketClient


class WebSocketTimeframesTest(unittest.TestCase):
    def test_candlestick_channels_grouped_by_timeframe(self) -> None:
        ws = DeltaWebSocketClient(
            websocket_url="wss://example",
            symbols=["BTCUSD", "ETHUSD", "XAUTUSD"],
            timeframe_by_symbol={
                "BTCUSD": "5m",
                "ETHUSD": "15m",
                "XAUTUSD": "5m",
            },
            retry_count=1,
            retry_delay=1,
        )
        channels = ws._candlestick_channels()
        names = {c["name"]: sorted(c["symbols"]) for c in channels}
        self.assertEqual(names["candlestick_15m"], ["ETHUSD"])
        self.assertEqual(names["candlestick_5m"], ["BTCUSD", "XAUTUSD"])


if __name__ == "__main__":
    unittest.main()
