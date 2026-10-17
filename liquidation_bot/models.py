from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LiquidationEvent:
    exchange: str
    symbol: str
    side: str
    price: float
    quantity: float
    timestamp_ms: int

    @property
    def usd_value(self) -> float:
        return self.price * self.quantity


@dataclass(frozen=True, slots=True)
class MarketContext:
    bingx_symbol: str
    current_price: float
    price_move_percent: float
    volume_ratio: float
    open_interest: float | None = None
    funding_rate: float | None = None


@dataclass(frozen=True, slots=True)
class Cascade:
    symbol: str
    side: str
    total_usd: float
    dominant_usd: float
    opposing_usd: float
    event_count: int
    dominance: float
    window_minutes: int
    started_ms: int
    ended_ms: int
    exchanges: tuple[str, ...]
