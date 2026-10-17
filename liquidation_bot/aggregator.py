from __future__ import annotations

from collections import defaultdict, deque
from datetime import UTC, datetime

from .models import Cascade, LiquidationEvent


class CascadeAggregator:
    def __init__(self, window_minutes: int) -> None:
        self.window_ms = window_minutes * 60_000
        self.window_minutes = window_minutes
        self._events: dict[str, deque[LiquidationEvent]] = defaultdict(deque)
        self._daily: dict[str, dict[str, float]] = defaultdict(
            lambda: {"long": 0.0, "short": 0.0, "events": 0.0}
        )
        self._daily_date = datetime.now(UTC).date()

    def add(self, event: LiquidationEvent) -> Cascade:
        self._roll_daily_if_needed()
        events = self._events[event.symbol]
        events.append(event)
        cutoff = event.timestamp_ms - self.window_ms
        while events and events[0].timestamp_ms < cutoff:
            events.popleft()

        daily = self._daily[event.symbol]
        daily[event.side] += event.usd_value
        daily["events"] += 1

        long_usd = sum(e.usd_value for e in events if e.side == "long")
        short_usd = sum(e.usd_value for e in events if e.side == "short")
        dominant_side = "long" if long_usd >= short_usd else "short"
        dominant = max(long_usd, short_usd)
        opposing = min(long_usd, short_usd)
        total = dominant + opposing
        return Cascade(
            symbol=event.symbol,
            side=dominant_side,
            total_usd=total,
            dominant_usd=dominant,
            opposing_usd=opposing,
            event_count=len(events),
            dominance=(dominant / total) if total else 0.0,
            window_minutes=self.window_minutes,
            started_ms=events[0].timestamp_ms,
            ended_ms=events[-1].timestamp_ms,
            exchanges=tuple(sorted({e.exchange for e in events})),
        )

    def daily_snapshot(self) -> dict[str, dict[str, float]]:
        self._roll_daily_if_needed()
        return {symbol: values.copy() for symbol, values in self._daily.items()}

    def _roll_daily_if_needed(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._daily_date:
            self._daily.clear()
            self._daily_date = today
