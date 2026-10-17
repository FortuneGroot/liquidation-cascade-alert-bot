import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from liquidation_bot.aggregator import CascadeAggregator
from liquidation_bot.binance import BinanceLiquidationStream
from liquidation_bot.bybit import BybitLiquidationStream
from liquidation_bot.config import Settings
from liquidation_bot.filters import AlertGate
from liquidation_bot.models import LiquidationEvent, MarketContext


def settings() -> Settings:
    return Settings(
        discord_token="x",
        alert_channel_id="1",
        summary_channel_id="1",
        alert_role_id=None,
        symbols=("BTCUSDT",),
        window_minutes=5,
        minimum_events=2,
        minimum_direction_dominance=0.7,
        minimum_price_move_percent=0.5,
        minimum_volume_ratio=1.2,
        cooldown_minutes=30,
        daily_alert_budget=4,
        evaluation_cooldown_seconds=20,
        thresholds_usd={"BTCUSDT": 1_000_000, "default": 500_000},
        summary_hours_utc=(0,),
    )


class CoreTests(unittest.TestCase):
    def test_bybit_parser_and_documented_side(self):
        payload = {"topic": "allLiquidation.BTCUSDT", "data": [
            {"T": 10, "s": "BTCUSDT", "S": "Buy", "v": "10", "p": "100000"}
        ]}
        events = BybitLiquidationStream._parse(payload)
        self.assertEqual(events[0].side, "long")
        self.assertEqual(events[0].usd_value, 1_000_000)

    def test_binance_parser_and_forced_order_side(self):
        payload = {"e": "forceOrder", "E": 10, "o": {
            "s": "BTCUSDT", "S": "SELL", "q": "10", "p": "100000",
            "ap": "100000", "z": "10", "T": 10
        }}
        event = BinanceLiquidationStream._parse(payload)
        self.assertIsNotNone(event)
        self.assertEqual(event.side, "long")
        self.assertEqual(event.usd_value, 1_000_000)

    def test_aggregation_and_gate(self):
        agg = CascadeAggregator(5)
        now = int(time.time() * 1000)
        agg.add(LiquidationEvent("Bybit", "BTCUSDT", "long", 100_000, 6, now))
        cascade = agg.add(LiquidationEvent("Bybit", "BTCUSDT", "long", 100_000, 6, now + 1))
        gate = AlertGate(settings())
        self.assertTrue(gate.prequalifies(cascade))
        self.assertEqual(cascade.exchanges, ("Bybit",))
        context = MarketContext("BTC-USDT", 99_000, -1.0, 1.5)
        self.assertTrue(gate.qualifies_with_context(cascade, context))

    def test_wrong_price_direction_is_rejected(self):
        agg = CascadeAggregator(5)
        now = int(time.time() * 1000)
        agg.add(LiquidationEvent("Bybit", "BTCUSDT", "long", 100_000, 6, now))
        cascade = agg.add(LiquidationEvent("Bybit", "BTCUSDT", "long", 100_000, 6, now + 1))
        gate = AlertGate(settings())
        self.assertFalse(gate.qualifies_with_context(
            cascade, MarketContext("BTC-USDT", 101_000, 1.0, 2.0)
        ))

    def test_daily_budget_survives_restart(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            first = AlertGate(settings(), path)
            first.record_alert("BTCUSDT")
            second = AlertGate(settings(), path)
            self.assertEqual(second.remaining_budget, 3)


if __name__ == "__main__":
    unittest.main()
