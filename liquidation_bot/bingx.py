from __future__ import annotations

import asyncio
import logging

import aiohttp

from .models import MarketContext

LOGGER = logging.getLogger(__name__)
BASE_URL = "https://open-api.bingx.com"


class BingXClient:
    def __init__(self, session: aiohttp.ClientSession) -> None:
        self.session = session

    async def market_context(self, symbol: str) -> MarketContext:
        bingx_symbol = symbol.replace("USDT", "-USDT")
        klines_task = self._get(
            "/openApi/swap/v3/quote/klines",
            {"symbol": bingx_symbol, "interval": "1m", "limit": "30"},
        )
        oi_task = self._get(
            "/openApi/swap/v2/quote/openInterest", {"symbol": bingx_symbol}, optional=True
        )
        funding_task = self._get(
            "/openApi/swap/v2/quote/premiumIndex", {"symbol": bingx_symbol}, optional=True
        )
        klines, oi, funding = await asyncio.gather(klines_task, oi_task, funding_task)
        rows = klines.get("data") or []
        if len(rows) < 10:
            raise RuntimeError(f"Insufficient BingX candle data for {bingx_symbol}")

        # The API may return newest-first. Sort using the first timestamp-like field.
        rows = sorted(rows, key=lambda row: int(row[0] if isinstance(row, list) else row.get("time", 0)))
        closes = [float(row[4] if isinstance(row, list) else row["close"]) for row in rows]
        volumes = [float(row[5] if isinstance(row, list) else row["volume"]) for row in rows]
        recent = volumes[-5:]
        baseline = volumes[:-5]
        baseline_per_candle = sum(baseline) / max(1, len(baseline))
        volume_ratio = (sum(recent) / len(recent)) / baseline_per_candle if baseline_per_candle else 0.0
        start_price = closes[-6]
        current_price = closes[-1]
        move = ((current_price / start_price) - 1.0) * 100.0

        oi_value = _nested_float(oi, "openInterest")
        funding_value = _nested_float(funding, "lastFundingRate", "fundingRate")
        return MarketContext(
            bingx_symbol=bingx_symbol,
            current_price=current_price,
            price_move_percent=move,
            volume_ratio=volume_ratio,
            open_interest=oi_value,
            funding_rate=funding_value,
        )

    async def _get(self, path: str, params: dict[str, str], optional: bool = False) -> dict:
        try:
            async with self.session.get(BASE_URL + path, params=params, timeout=12) as response:
                response.raise_for_status()
                payload = await response.json()
                if str(payload.get("code", "0")) not in {"0", ""}:
                    raise RuntimeError(payload.get("msg", "BingX API error"))
                return payload
        except Exception:
            if optional:
                LOGGER.warning("Optional BingX request failed: %s", path, exc_info=True)
                return {}
            raise


def _nested_float(payload: dict, *keys: str) -> float | None:
    data = payload.get("data", payload)
    if isinstance(data, list) and data:
        data = data[0]
    if not isinstance(data, dict):
        return None
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return None

