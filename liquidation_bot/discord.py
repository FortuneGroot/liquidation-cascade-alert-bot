from __future__ import annotations

import asyncio
import logging

import aiohttp

from .models import Cascade, MarketContext

LOGGER = logging.getLogger(__name__)
API_ROOT = "https://discord.com/api/v10"


class DiscordClient:
    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self.session = session
        self.headers = {"Authorization": f"Bot {token}"}

    async def validate_channel(self, channel_id: str) -> None:
        async with self.session.get(
            f"{API_ROOT}/channels/{channel_id}", headers=self.headers, timeout=15
        ) as response:
            if response.status >= 400:
                raise RuntimeError(f"Discord channel check {response.status}: {await response.text()}")

    async def send_cascade(
        self,
        channel_id: str,
        cascade: Cascade,
        context: MarketContext,
        role_id: str | None,
    ) -> None:
        is_long = cascade.side == "long"
        color = 0xE74C3C if is_long else 0x2ECC71
        direction = "LONG" if is_long else "SHORT"
        pressure = "sell pressure" if is_long else "buy pressure"
        description = (
            f"**{_money(cascade.dominant_usd)} in observed {cascade.side} liquidations** "
            f"over {cascade.window_minutes} minutes across {', '.join(cascade.exchanges)}. Forced closures are contributing "
            f"to abnormal {pressure}."
        )
        fields = [
            {"name": "BingX Price", "value": f"${context.current_price:,.6g}", "inline": True},
            {"name": "5m Price Move", "value": f"{context.price_move_percent:+.2f}%", "inline": True},
            {"name": "Volume vs Baseline", "value": f"{context.volume_ratio:.2f}×", "inline": True},
            {"name": "Observed Events", "value": str(cascade.event_count), "inline": True},
            {"name": "Directional Share", "value": f"{cascade.dominance:.0%}", "inline": True},
            {"name": "Liquidation Sources", "value": ", ".join(cascade.exchanges), "inline": True},
            {"name": "Market Context", "value": "BingX perpetuals", "inline": True},
        ]
        if context.funding_rate is not None:
            fields.append({"name": "BingX Funding", "value": f"{context.funding_rate:.4%}", "inline": True})
        content = f"<@&{role_id}>" if role_id else ""
        await self._post(
            channel_id,
            {
                "content": content,
                "allowed_mentions": {"roles": [role_id]} if role_id else {"parse": []},
                "embeds": [{
                    "title": f"🚨 Major {direction} Liquidation Cascade — {cascade.symbol}",
                    "description": description,
                    "color": color,
                    "fields": fields,
                    "footer": {"text": "Market-pressure alert, not a trade instruction."},
                }],
            },
        )

    async def send_summary(self, channel_id: str, snapshot: dict[str, dict[str, float]]) -> None:
        ranked = sorted(snapshot.items(), key=lambda item: item[1]["long"] + item[1]["short"], reverse=True)[:8]
        if not ranked:
            return
        lines = []
        for symbol, values in ranked:
            total = values["long"] + values["short"]
            dominant = "longs" if values["long"] >= values["short"] else "shorts"
            lines.append(f"**{symbol}** — {_money(total)} observed; {dominant} dominant")
        await self._post(
            channel_id,
            {
                "allowed_mentions": {"parse": []},
                "embeds": [{
                    "title": "Liquidation Market Summary",
                    "description": "\n".join(lines),
                    "color": 0x5865F2,
                    "footer": {"text": "Observed Binance + Bybit events today • No notification mention"},
                }],
            },
        )

    async def _post(self, channel_id: str, payload: dict) -> None:
        url = f"{API_ROOT}/channels/{channel_id}/messages"
        for attempt in range(4):
            async with self.session.post(url, headers=self.headers, json=payload, timeout=15) as response:
                if response.status == 429:
                    body = await response.json()
                    await asyncio.sleep(float(body.get("retry_after", 1)))
                    continue
                if response.status >= 400:
                    raise RuntimeError(f"Discord API {response.status}: {await response.text()}")
                LOGGER.info("Sent Discord message to channel %s", channel_id)
                return
        raise RuntimeError("Discord rate limit retry budget exhausted")


def _money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    return f"${value / 1_000:.0f}K"
