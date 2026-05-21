from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from typing import Any

import websockets
from websockets.client import WebSocketClientProtocol

from utils.helpers import Candle, CriticalBotError, normalize_candle_timestamp


class DeltaWebSocketClient:
    def __init__(
        self,
        websocket_url: str,
        symbols: list[str],
        timeframe_by_symbol: dict[str, str],
        retry_count: int,
        retry_delay: int,
        history_limit: int = 200,
        logger: logging.Logger | None = None,
    ) -> None:
        self.websocket_url = websocket_url
        self.symbols = symbols
        self.timeframe_by_symbol = {s: timeframe_by_symbol[s] for s in symbols if s in timeframe_by_symbol}
        for sym in symbols:
            if sym not in self.timeframe_by_symbol:
                raise CriticalBotError(f"No timeframe configured for websocket symbol {sym}")
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.logger = logger
        self.connected = False
        self.last_message_at = 0.0
        self._stop = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._candles: dict[str, deque[Candle]] = {
            symbol: deque(maxlen=history_limit) for symbol in symbols
        }
        self._prices: dict[str, float] = {symbol: 0.0 for symbol in symbols}

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="delta-websocket")

    async def stop(self) -> None:
        self._stop.set()
        if self._task and not self._task.done():
            self._task.cancel()
        if self._task:
            await asyncio.wait_for(asyncio.gather(self._task, return_exceptions=True), timeout=5)

    def latest_price(self, symbol: str) -> float:
        return self._prices.get(symbol, 0.0)

    def candles(self, symbol: str) -> list[Candle]:
        return list(self._candles.get(symbol, ()))

    def status(self) -> str:
        if self._task and not self._task.done() and not self.connected:
            return "CONNECTING"
        if not self.connected:
            return "DISCONNECTED"
        if time.time() - self.last_message_at > 120:
            return "STALE"
        return "CONNECTED"

    def raise_if_failed(self) -> None:
        if self._task and self._task.done():
            error = self._task.exception()
            if error:
                raise CriticalBotError(str(error)) from error

    async def _run(self) -> None:
        failures = 0
        while not self._stop.is_set():
            try:
                if self.logger:
                    self.logger.info("Connecting websocket: %s", self.websocket_url)
                async with websockets.connect(self.websocket_url, ping_interval=20, ping_timeout=10) as ws:
                    failures = 0
                    self.connected = True
                    self.last_message_at = time.time()
                    if self.logger:
                        self.logger.info("Websocket connected")
                    await self._subscribe(ws)
                    await self._consume(ws)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                failures += 1
                if self.logger:
                    self.logger.warning("Websocket reconnect %s/%s after error: %s", failures, self.retry_count, exc)
                if failures >= self.retry_count:
                    raise CriticalBotError(f"Permanent websocket failure: {exc}") from exc
                await asyncio.sleep(self.retry_delay)

    def _candlestick_channels(self) -> list[dict[str, Any]]:
        """Group symbols by timeframe for separate candlestick_* subscriptions."""
        by_tf: dict[str, list[str]] = {}
        for symbol in self.symbols:
            tf = self.timeframe_by_symbol[symbol]
            by_tf.setdefault(tf, []).append(symbol)
        return [
            {"name": f"candlestick_{tf}", "symbols": syms}
            for tf, syms in sorted(by_tf.items())
        ]

    async def _subscribe(self, ws: WebSocketClientProtocol) -> None:
        channels: list[dict[str, Any]] = [
            {"name": "v2/ticker", "symbols": self.symbols},
            *self._candlestick_channels(),
        ]
        payload = {"type": "subscribe", "payload": {"channels": channels}}
        await ws.send(json.dumps(payload))
        if self.logger:
            channel_names = ", ".join(channel["name"] for channel in channels)
            self.logger.info("Websocket subscribed | channels=%s | symbols=%s", channel_names, ",".join(self.symbols))

    async def _consume(self, ws: WebSocketClientProtocol) -> None:
        async for raw in ws:
            if self._stop.is_set():
                return
            self.last_message_at = time.time()
            message = json.loads(raw)
            self._handle_message(message)

    def _handle_message(self, message: dict[str, Any]) -> None:
        symbol = _message_symbol(message)
        if not symbol or symbol not in self.symbols:
            return
        price = _first_float(message, ("mark_price", "close", "price", "c", "p", "m"))
        if price:
            self._prices[symbol] = price
        if not _is_candlestick_message(message):
            return
        timeframe = self.timeframe_by_symbol[symbol]
        candle = _message_to_candle(message, timeframe)
        if candle:
            candles = self._candles[symbol]
            if candles and candles[-1].timestamp == candle.timestamp:
                candles[-1] = candle
            else:
                candles.append(candle)


def _first_float(message: dict[str, Any], keys: tuple[str, ...]) -> float:
    for key in keys:
        value = message.get(key)
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                continue
    return 0.0


def _message_symbol(message: dict[str, Any]) -> str:
    symbol = str(message.get("symbol") or message.get("sy") or message.get("s") or "")
    return symbol.removeprefix("MARK:")


def _is_candlestick_message(message: dict[str, Any]) -> bool:
    return str(message.get("type", "")).startswith("candlestick_")


def _message_to_candle(message: dict[str, Any], timeframe: str) -> Candle | None:
    keys = ("open", "high", "low", "close")
    short_keys = ("o", "h", "l", "c")
    if not (all(key in message for key in keys) or all(key in message for key in short_keys)):
        return None
    timestamp = normalize_candle_timestamp(
        int(message.get("timestamp") or message.get("time") or message.get("ts") or time.time()),
        timeframe,
    )
    return Candle(
        timestamp=timestamp,
        open=_first_float(message, ("open", "o")),
        high=_first_float(message, ("high", "h")),
        low=_first_float(message, ("low", "l")),
        close=_first_float(message, ("close", "c")),
        volume=_first_float(message, ("volume", "v")),
    )
