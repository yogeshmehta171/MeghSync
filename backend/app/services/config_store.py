"""Runtime settings that officials can change from the dashboard. Cached in memory, persisted in app_config."""
from __future__ import annotations

from typing import Any

from .risk import DEFAULT_THRESHOLDS, LEVELS, validate_thresholds

DEFAULTS: dict[str, Any] = {
    "thresholds": dict(DEFAULT_THRESHOLDS),
    "alert_min_level": "MODERATE",          # alerts are raised from this level upward
    "log_retention_days": 90,               # 0 = keep forever
    "prediction_retention_days": 7,
    "alert_retention_days": 90,
}


def validate_value(key: str, value: Any) -> Any:
    if key == "thresholds":
        return validate_thresholds(value)
    if key == "alert_min_level":
        if value not in LEVELS[1:]:
            raise ValueError(f"alert_min_level must be one of {LEVELS[1:]}")
        return value
    if key in ("log_retention_days", "prediction_retention_days", "alert_retention_days"):
        v = int(value)
        if not (0 <= v <= 3650):
            raise ValueError(f"{key} must be between 0 and 3650")
        if key == "prediction_retention_days" and v == 0:
            raise ValueError("prediction_retention_days cannot be 0 (would grow without limit)")
        return v
    raise ValueError(f"unknown setting '{key}'")


class ConfigStore:
    def __init__(self, pool):
        self.pool = pool
        self.values: dict[str, Any] = {k: (dict(v) if isinstance(v, dict) else v) for k, v in DEFAULTS.items()}

    async def load(self) -> None:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT key, value FROM app_config")
        for r in rows:
            if r["key"] in DEFAULTS:
                try:
                    self.values[r["key"]] = validate_value(r["key"], r["value"])
                except ValueError:
                    pass                                    # a bad stored value falls back to the default

    async def update(self, changes: dict[str, Any], who: str) -> dict[str, Any]:
        clean = {k: validate_value(k, v) for k, v in changes.items()}
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                for k, v in clean.items():
                    await conn.execute(
                        "INSERT INTO app_config(key, value, updated_by) VALUES ($1, $2, $3) "
                        "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_by = EXCLUDED.updated_by, "
                        "updated_at = now()", k, v, who)
        self.values.update(clean)
        return self.values

    @property
    def thresholds(self) -> dict[str, float]:
        return self.values["thresholds"]
