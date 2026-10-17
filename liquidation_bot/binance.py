from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

import aiohttp

from .models import LiquidationEvent

LOGGER = logging.getLogger(__name__)
# Current Binance USD-M all-market liquidation endpoint.
WS_URL = "wss://fstream.binance.com/market/ws/!forceOrder@arr"


class BinanceLiquidationStream:
    """Binance USD-M all-market liquidation stream (public, no API key)."""

    def __init__(self, session: aiohttp.ClientSession, symbols: tuple[str, ...]) -> None:
        self.session = session
        self.symbols = set(symbols)

    async def events(self) -> AsyncIterator[LiquidationEvent]:
        backoff = 1
        while True:
            try:
                async with self.session.ws_connect(WS_URL, heartbeat=20, receive_timeout=45) as ws:
                    LOGGER.info("Connected to Binance USD-M liquidation stream")
                    backoff = 1
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            payload = json.loads(message.data)
                            event = self._parse(payload)
                            if event and event.symbol in self.symbols:
                                yield event
                        elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                            break
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Binance stream disconnected; reconnecting in %ss", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    @staticmethod
    def _parse(payload: dict) -> LiquidationEvent | None:
        if payload.get("e") != "forceOrder":
            return None
        row = payload.get("o") or {}
        try:
            price = float(row.get("ap") or row.get("p"))
            quantity = float(row.get("z") or row.get("q"))
            # A forced SELL closes a long; a forced BUY closes a short.
            side = "long" if row["S"] == "SELL" else "short"
            return LiquidationEvent(
                exchange="Binance",
                symbol=str(row["s"]).upper(),
                side=side,
                price=price,
                quantity=quantity,
                timestamp_ms=int(row.get("T", payload.get("E", time.time_ns() // 1_000_000))),
            )
        except (KeyError, TypeError, ValueError):
            LOGGER.warning("Ignoring malformed Binance liquidation event: %r", payload)
            return None
