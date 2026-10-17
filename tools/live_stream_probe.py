"""Read-only WebSocket handshake check for Binance and Bybit."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from liquidation_bot.binance import WS_URL as BINANCE_WS_URL
from liquidation_bot.bybit import WS_URL as BYBIT_WS_URL


async def check_binance(session: aiohttp.ClientSession) -> None:
    async with session.ws_connect(BINANCE_WS_URL, heartbeat=20) as ws:
        print("Binance connected:", not ws.closed)


async def check_bybit(session: aiohttp.ClientSession) -> None:
    async with session.ws_connect(BYBIT_WS_URL, heartbeat=20) as ws:
        await ws.send_json({"op": "subscribe", "args": ["allLiquidation.BTCUSDT"]})
        acknowledgement = await asyncio.wait_for(ws.receive_json(), timeout=10)
        print("Bybit subscribed:", acknowledgement.get("success") is True)


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        await asyncio.gather(check_binance(session), check_bybit(session))


if __name__ == "__main__":
    asyncio.run(main())
