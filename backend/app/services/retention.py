"""Hourly clean-up so history tables cannot grow forever. Retention periods come from app_config."""
from __future__ import annotations

import asyncio
import logging

log = logging.getLogger("pravaha.retention")

STATEMENTS = [
    ("log_retention_days",        "DELETE FROM actions WHERE ts < now() - make_interval(days => $1)"),
    ("prediction_retention_days", "DELETE FROM node_predictions WHERE ts < now() - make_interval(days => $1)"),
    ("prediction_retention_days", "DELETE FROM prediction_snapshots WHERE ts < now() - make_interval(days => $1)"),
    ("alert_retention_days",      "DELETE FROM alerts WHERE resolved_at IS NOT NULL AND resolved_at < now() - make_interval(days => $1)"),
    ("prediction_retention_days", "DELETE FROM route_requests WHERE ts < now() - make_interval(days => GREATEST($1, 30))"),
]


async def run_once(pool, cfg) -> dict:
    deleted = {}
    async with pool.acquire() as conn:
        for key, sql in STATEMENTS:
            days = int(cfg.values[key])
            if days == 0:                                    # 0 = keep forever (not allowed for predictions)
                continue
            tag = await conn.execute(sql, days)
            deleted[sql.split()[2]] = int(tag.split()[-1])
    return deleted


async def loop(pool, cfg, every_seconds: float = 3600.0) -> None:
    while True:
        try:
            d = await run_once(pool, cfg)
            if any(d.values()):
                log.info("retention deleted %s", d)
        except Exception:
            log.exception("retention run failed")
        await asyncio.sleep(every_seconds)
