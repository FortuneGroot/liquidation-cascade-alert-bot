from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator

import aiohttp

from .models import LiquidationEvent

LOGGER = logging.getLogger(__name__)
WS_URL = "wss://stream.bybit.com/v5/public/linear"


class BybitLiquidationStream:
    def __init__(self, session: aiohttp.ClientSession, symbols: tuple[str, ...]) -> None:
        self.session = session
        self.symbols = symbols

    async def events(self) -> AsyncIterator[LiquidationEvent]:
        backoff = 1
        while True:
            try:
                async with self.session.ws_connect(WS_URL, heartbeat=20, receive_timeout=45) as ws:
                    args = [f"allLiquidation.{symbol}" for symbol in self.symbols]
                    await ws.send_json({"op": "subscribe", "args": args})
                    LOGGER.info("Connected to Bybit liquidation stream for %d symbols", len(args))
                    backoff = 1
                    async for message in ws:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            payload = json.loads(message.data)
                            for event in self._parse(payload):
                                yield event
                        elif message.type in {aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR}:
                            break
            except asyncio.CancelledError:
                raise
            except Exception:
                LOGGER.exception("Bybit stream disconnected; reconnecting in %ss", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 60)

    @staticmethod
    def _parse(payload: dict) -> list[LiquidationEvent]:
        if not str(payload.get("topic", "")).startswith("allLiquidation."):
            return []
        parsed: list[LiquidationEvent] = []
        for row in payload.get("data", []):
            try:
                # Bybit documents Buy as a liquidated long and Sell as a liquidated short.
                side = "long" if row["S"] == "Buy" else "short"
                parsed.append(
                    LiquidationEvent(
                        exchange="Bybit",
                        symbol=str(row["s"]).upper(),
                        side=side,
                        price=float(row["p"]),
                        quantity=float(row["v"]),
                        timestamp_ms=int(row.get("T", time.time_ns() // 1_000_000)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                LOGGER.warning("Ignoring malformed liquidation event: %r", row)
        return parsed

