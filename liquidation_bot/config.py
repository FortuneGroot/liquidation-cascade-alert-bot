from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    alert_channel_id: str
    summary_channel_id: str
    alert_role_id: str | None
    symbols: tuple[str, ...]
    window_minutes: int
    minimum_events: int
    minimum_direction_dominance: float
    minimum_price_move_percent: float
    minimum_volume_ratio: float
    cooldown_minutes: int
    daily_alert_budget: int
    evaluation_cooldown_seconds: int
    thresholds_usd: dict[str, float]
    summary_hours_utc: tuple[int, ...]

    def threshold_for(self, symbol: str) -> float:
        return float(self.thresholds_usd.get(symbol, self.thresholds_usd["default"]))


def load_settings(base_dir: Path | None = None) -> Settings:
    base_dir = base_dir or Path.cwd()
    load_dotenv(base_dir / ".env")
    config_path = Path(os.getenv("BOT_CONFIG", base_dir / "config.json"))
    if not config_path.exists():
        config_path = base_dir / "config.example.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))

    token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
    alert_channel = os.getenv("DISCORD_ALERT_CHANNEL_ID", "").strip()
    summary_channel = os.getenv("DISCORD_SUMMARY_CHANNEL_ID", alert_channel).strip()
    if not token or not alert_channel:
        raise RuntimeError("DISCORD_BOT_TOKEN and DISCORD_ALERT_CHANNEL_ID are required")

    role = os.getenv("DISCORD_ALERT_ROLE_ID", "").strip() or None
    return Settings(
        discord_token=token,
        alert_channel_id=alert_channel,
        summary_channel_id=summary_channel or alert_channel,
        alert_role_id=role,
        symbols=tuple(s.upper() for s in data["symbols"]),
        window_minutes=int(data["window_minutes"]),
        minimum_events=int(data["minimum_events"]),
        minimum_direction_dominance=float(data["minimum_direction_dominance"]),
        minimum_price_move_percent=float(data["minimum_price_move_percent"]),
        minimum_volume_ratio=float(data["minimum_volume_ratio"]),
        cooldown_minutes=int(data["cooldown_minutes"]),
        daily_alert_budget=int(data["daily_alert_budget"]),
        evaluation_cooldown_seconds=int(data["evaluation_cooldown_seconds"]),
        thresholds_usd={k: float(v) for k, v in data["thresholds_usd"].items()},
        summary_hours_utc=tuple(int(v) for v in data["summary_hours_utc"]),
    )

