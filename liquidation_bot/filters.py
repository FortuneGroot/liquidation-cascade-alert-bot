from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from .config import Settings
from .models import Cascade, MarketContext


class AlertGate:
    def __init__(self, settings: Settings, state_path: Path | None = None) -> None:
        self.settings = settings
        self.state_path = state_path
        self._last_alert: dict[str, datetime] = {}
        self._budget_date = datetime.now(UTC).date()
        self._alerts_today = 0
        self._load_state()

    def prequalifies(self, cascade: Cascade) -> bool:
        self._roll_budget()
        if self._alerts_today >= self.settings.daily_alert_budget:
            return False
        if cascade.dominant_usd < self.settings.threshold_for(cascade.symbol):
            return False
        if cascade.event_count < self.settings.minimum_events:
            return False
        if cascade.dominance < self.settings.minimum_direction_dominance:
            return False
        last = self._last_alert.get(cascade.symbol)
        if last and datetime.now(UTC) - last < timedelta(minutes=self.settings.cooldown_minutes):
            return False
        return True

    def qualifies_with_context(self, cascade: Cascade, context: MarketContext) -> bool:
        if abs(context.price_move_percent) < self.settings.minimum_price_move_percent:
            return False
        if context.volume_ratio < self.settings.minimum_volume_ratio:
            return False
        if cascade.side == "long" and context.price_move_percent >= 0:
            return False
        if cascade.side == "short" and context.price_move_percent <= 0:
            return False
        return True

    def record_alert(self, symbol: str) -> None:
        self._roll_budget()
        self._last_alert[symbol] = datetime.now(UTC)
        self._alerts_today += 1
        self._save_state()

    @property
    def remaining_budget(self) -> int:
        self._roll_budget()
        return max(0, self.settings.daily_alert_budget - self._alerts_today)

    def _roll_budget(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._budget_date:
            self._budget_date = today
            self._alerts_today = 0
            self._last_alert.clear()
            self._save_state()

    def _load_state(self) -> None:
        if not self.state_path:
            return
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            if payload.get("date") != self._budget_date.isoformat():
                return
            self._alerts_today = int(payload.get("alerts_today", 0))
            self._last_alert = {
                symbol: datetime.fromisoformat(value)
                for symbol, value in payload.get("last_alert", {}).items()
            }
        except (FileNotFoundError, ValueError, TypeError, json.JSONDecodeError):
            return

    def _save_state(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "date": self._budget_date.isoformat(),
            "alerts_today": self._alerts_today,
            "last_alert": {symbol: value.isoformat() for symbol, value in self._last_alert.items()},
        }
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
