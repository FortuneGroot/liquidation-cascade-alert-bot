from __future__ import annotations

import asyncio
import logging
import time
from datetime import UTC, datetime
from pathlib import Path

import aiohttp

from .aggregator import CascadeAggregator
from .binance import BinanceLiquidationStream
from .bingx import BingXClient
from .bybit import BybitLiquidationStream
from .config import Settings, load_settings
from .discord import DiscordClient
from .filters import AlertGate

LOGGER = logging.getLogger(__name__)


class LiquidationBot:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.aggregator = CascadeAggregator(settings.window_minutes)
        self.gate = AlertGate(settings, Path("data/alert_state.json"))
        self._last_evaluation_ms: dict[str, int] = {}

    async def run(self) -> None:
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            streams = (
                BinanceLiquidationStream(session, self.settings.symbols),
                BybitLiquidationStream(session, self.settings.symbols),
            )
            bingx = BingXClient(session)
            discord = DiscordClient(session, self.settings.discord_token)
            await discord.validate_channel(self.settings.alert_channel_id)
            if self.settings.summary_channel_id != self.settings.alert_channel_id:
                await discord.validate_channel(self.settings.summary_channel_id)
            LOGGER.info("Discord channels validated")
            event_queue: asyncio.Queue = asyncio.Queue(maxsize=10_000)
            stream_tasks = [asyncio.create_task(self._pump_stream(stream, event_queue)) for stream in streams]
            summary_task = asyncio.create_task(self._summary_loop(discord))
            try:
                while True:
                    event = await event_queue.get()
                    cascade = self.aggregator.add(event)
                    if not self.gate.prequalifies(cascade):
                        continue
                    now_ms = time.time_ns() // 1_000_000
                    last_eval = self._last_evaluation_ms.get(event.symbol, 0)
                    if now_ms - last_eval < self.settings.evaluation_cooldown_seconds * 1000:
                        continue
                    self._last_evaluation_ms[event.symbol] = now_ms
                    try:
                        context = await bingx.market_context(event.symbol)
                    except Exception:
                        LOGGER.exception("Could not obtain BingX context for %s", event.symbol)
                        continue
                    if not self.gate.qualifies_with_context(cascade, context):
                        continue
                    await discord.send_cascade(
                        self.settings.alert_channel_id,
                        cascade,
                        context,
                        self.settings.alert_role_id,
                    )
                    self.gate.record_alert(event.symbol)
                    LOGGER.warning(
                        "ALERT %s %s %.2f remaining_budget=%d",
                        cascade.symbol,
                        cascade.side,
                        cascade.dominant_usd,
                        self.gate.remaining_budget,
                    )
            finally:
                for task in stream_tasks:
                    task.cancel()
                summary_task.cancel()
                await asyncio.gather(*stream_tasks, summary_task, return_exceptions=True)

    @staticmethod
    async def _pump_stream(stream, queue: asyncio.Queue) -> None:
        async for event in stream.events():
            await queue.put(event)

    async def _summary_loop(self, discord: DiscordClient) -> None:
        sent: set[tuple[object, int]] = set()
        while True:
            now = datetime.now(UTC)
            key = (now.date(), now.hour)
            if now.hour in self.settings.summary_hours_utc and now.minute < 2 and key not in sent:
                await discord.send_summary(self.settings.summary_channel_id, self.aggregator.daily_snapshot())
                sent.add(key)
                sent = {item for item in sent if item[0] == now.date()}
            await asyncio.sleep(30)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings(Path.cwd())
    asyncio.run(LiquidationBot(settings).run())


if __name__ == "__main__":
    main()
