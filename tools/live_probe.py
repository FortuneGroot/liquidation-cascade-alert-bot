"""Read-only connectivity check for the public BingX market-context API."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import aiohttp

from liquidation_bot.bingx import BingXClient


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        context = await BingXClient(session).market_context("BTCUSDT")
        print(context)


if __name__ == "__main__":
    asyncio.run(main())
