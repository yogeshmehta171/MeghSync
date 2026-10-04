"""
The engine owns the live state: the model, the rain input, the latest predictions, and the 5-second loop.

IMPORTANT: state is in this process's RAM, so the server must run as ONE worker (uvicorn without --workers).
Each tick advances the model by one 5-minute step ("simulation clock"); a production deployment feeding real
rain gauges would set INFERENCE_INTERVAL_SECONDS=300 so simulated time equals wall-clock time.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from ..config import Settings
from ..db import (COUNT_PENALIZED, COUNT_ROUTE_BLOCKING, FLOOD_PENALTY_UPDATE, LOAD_NODES, NETWORK_BBOX,
                  SYNC_OVERRIDES, UPDATE_MANHOLE_FLOOD)
from ..model.base import FORECAST_HORIZONS, ModelProvider
from ..model.factory import build_provider
from .actions import log_action
from .config_store import ConfigStore
from .risk import LEVELS, LEVEL_RANK, level_for_depth

log = logging.getLogger("pravaha.engine")

ALERT_RESOLVE = ("UPDATE alerts SET resolved_at = now() "
                 "WHERE resolved_at IS NULL AND NOT (node_id = ANY($1::text[]))")
_ALERT_ROWS = ("SELECT unnest($1::text[]) AS node_id, unnest($2::text[]) AS level, unnest($3::int[]) AS rank, "
               "unnest($4::double precision[]) AS depth, unnest($5::text[]) AS msg")
ALERT_UPDATE = f"""
UPDATE alerts a SET level = x.level, level_rank = x.rank, peak_rank = GREATEST(a.peak_rank, x.rank),
       depth_m = x.depth, message = x.msg, updated_at = now()
FROM ({_ALERT_ROWS}) x
WHERE a.node_id = x.node_id AND a.resolved_at IS NULL
  AND (a.level_rank <> x.rank OR abs(a.depth_m - x.depth) > 0.02);
"""
ALERT_INSERT = f"""
INSERT INTO alerts(node_id, level, level_rank, peak_rank, depth_m, message)
SELECT x.node_id, x.level, x.rank, x.rank, x.depth, x.msg FROM ({_ALERT_ROWS}) x
WHERE NOT EXISTS (SELECT 1 FROM alerts a WHERE a.node_id = x.node_id AND a.resolved_at IS NULL)
ON CONFLICT DO NOTHING;
"""
INSERT_SNAPSHOT = ("INSERT INTO prediction_snapshots(ts, horizon_min, rain_mm_hr, max_flood_m, wet_nodes, "
                   "blocking_nodes, model) VALUES (to_timestamp($1), $2, $3, $4, $5, $6, $7)")
INSERT_NODE_PRED = ("INSERT INTO node_predictions(ts, horizon_min, node_id, flood_m) "
                    "SELECT to_timestamp($1), $2::int, x.id, x.f FROM "
                    "(SELECT unnest($3::text[]) AS id, unnest($4::real[]) AS f) x")


@dataclass
class Snapshot:
    computed_at: float
    rain_mm_hr: float
    flood_m: np.ndarray
    depth_m: np.ndarray
    forecasts: dict                      # steps -> flood_m [N]
    forecast_ms: int
    route_blocking_count: int
    penalized_streets: int


class Engine:
    def __init__(self, settings: Settings, pool):
        self.settings, self.pool = settings, pool
        self.cfg = ConfigStore(pool)
        self.provider: Optional[ModelProvider] = None
        self.snapshot: Optional[Snapshot] = None
        self.node_ids: list[str] = []
        self.node_index: dict[str, int] = {}
        self.lat = self.lon = self.max_depth = None
        self.meta: list[dict] = []
        self.bbox = (0.0, 0.0, 0.0, 0.0)
        self.pending_rain = 0.0
        self.capacity: Optional[np.ndarray] = None         # [E] or None = all clear
        self.blocks: dict[str, dict] = {}                    # node_id -> {source, note, created_at, report_ref}
        self.last_error: Optional[str] = None
        self._infer_lock = asyncio.Lock()
        self._state_lock = asyncio.Lock()
        self._tasks: list[asyncio.Task] = []
        self._last_sample = 0.0
        self.recent: deque = deque(maxlen=60)                # (unix_ts, flood_m[N]) of the last 60 live ticks

    # ------------------------------------------------------------------ lifecycle
    async def start(self) -> None:
        await self.cfg.load()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(LOAD_NODES)
            if not rows:
                raise RuntimeError("manholes table is empty -- run scripts/load_data.py first")
            bb = await conn.fetchrow(NETWORK_BBOX)
        m = self.settings.bbox_margin_deg
        self.bbox = (bb["min_lon"] - m, bb["min_lat"] - m, bb["max_lon"] + m, bb["max_lat"] + m)
        self.node_ids = [r["id"] for r in rows]
        self.node_index = {nid: i for i, nid in enumerate(self.node_ids)}
        self.lat = np.array([r["lat"] for r in rows])
        self.lon = np.array([r["lon"] for r in rows])
        self.max_depth = np.array([r["max_depth_m"] for r in rows], dtype=np.float32)
        self.meta = [{"location": r["location"], "elevation_m": r["elevation_m"],
                      "imperviousness_pct": r["imperviousness_pct"]} for r in rows]

        self.provider = await asyncio.to_thread(build_provider, self.settings, len(self.node_ids))
        log.info("model provider=%s version=%s nodes=%d", self.provider.name, self.provider.version, len(self.node_ids))

        await self.refresh_blocks()
        await self.tick()                                    # fail loudly at startup if inference is broken
        self._tasks = [asyncio.create_task(self._loop(), name="inference-loop")]

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    async def _loop(self) -> None:
        while True:
            await asyncio.sleep(self.settings.inference_interval_seconds)
            try:
                await self.tick()
                self.last_error = None
            except Exception as e:                           # keep serving the last good snapshot
                self.last_error = repr(e)
                log.exception("tick failed")

    # ------------------------------------------------------------------ one tick
    def _compute(self, rain: float, capacity):
        live = self.provider.step(rain, capacity)
        steps = [h["steps"] for h in FORECAST_HORIZONS]
        t0 = time.perf_counter()
        fc = self.provider.forecast(rain, capacity, steps)
        return live, fc, round((time.perf_counter() - t0) * 1000)

    async def tick(self) -> None:
        async with self._infer_lock:
            async with self._state_lock:
                rain = self.pending_rain
                cap = None if self.capacity is None else self.capacity.copy()
            live, fc, fc_ms = await asyncio.to_thread(self._compute, rain, cap)
            th = self.cfg.thresholds
            flood = live.flood_m
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(UPDATE_MANHOLE_FLOOD, self.node_ids, float(th["route_block_m"]), flood.tolist())
                    await conn.execute(FLOOD_PENALTY_UPDATE, self.settings.spatial_join_radius_m,
                                       self.settings.flood_cost_multiplier)
                    penalized = await conn.fetchval(COUNT_PENALIZED)
                    blocking = await conn.fetchval(COUNT_ROUTE_BLOCKING)
                    await self._update_alerts(conn, flood)
            snap = Snapshot(time.time(), rain, flood.copy(), live.depth_m.copy(), fc, fc_ms, int(blocking), int(penalized))
            async with self._state_lock:
                self.snapshot = snap
                self.recent.append((snap.computed_at, snap.flood_m.copy()))
            await self._maybe_sample(snap)

    # ------------------------------------------------------------------ alerts
    async def _update_alerts(self, conn, flood: np.ndarray) -> None:
        th = self.cfg.thresholds
        min_level = self.cfg.values["alert_min_level"]
        min_rank = LEVEL_RANK[min_level]
        min_depth = {"LOW": th["low_m"], "MODERATE": th["moderate_m"], "HIGH": th["high_m"],
                     "CRITICAL": th["critical_m"]}[min_level]
        keep_depth = 0.8 * min_depth                         # hysteresis: avoids open/close flapping at the threshold
        ids, lv, rk, dp, ms = [], [], [], [], []
        keep = []
        for i in np.nonzero(flood >= keep_depth)[0]:
            nid, d = self.node_ids[i], float(flood[i])
            keep.append(nid)
            level = level_for_depth(d, th)
            if LEVEL_RANK[level] >= min_rank:
                ids.append(nid); lv.append(level); rk.append(LEVEL_RANK[level]); dp.append(d)
                ms.append(f"{nid}: {level} - surface flood {d * 100:.0f} cm")
        await conn.execute(ALERT_RESOLVE, keep)
        if ids:
            await conn.execute(ALERT_UPDATE, ids, lv, rk, dp, ms)
            await conn.execute(ALERT_INSERT, ids, lv, rk, dp, ms)

    # ------------------------------------------------------------------ history sampling
    async def _maybe_sample(self, snap: Snapshot) -> None:
        if snap.computed_at - self._last_sample < self.settings.prediction_sample_seconds:
            return
        self._last_sample = snap.computed_at
        th = self.cfg.thresholds
        model = f"{self.provider.name}:{self.provider.version}"
        rows = [(0, snap.flood_m)] + [(h["steps"] * 5, snap.forecasts[h["steps"]]) for h in FORECAST_HORIZONS]
        try:
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    for minutes, arr in rows:
                        wet = np.nonzero(arr >= 0.01)[0]
                        await conn.execute(INSERT_SNAPSHOT, snap.computed_at, minutes, snap.rain_mm_hr, float(arr.max()),
                                           int(len(wet)), int((arr >= th["route_block_m"]).sum()), model)
                        if len(wet):
                            await conn.execute(INSERT_NODE_PRED, snap.computed_at, minutes,
                                               [self.node_ids[i] for i in wet], [float(arr[i]) for i in wet])
        except Exception:
            log.exception("prediction sampling failed (non-fatal)")

    # ------------------------------------------------------------------ controls
    async def set_rain(self, mm_hr: float) -> None:
        async with self._state_lock:
            self.pending_rain = float(mm_hr)

    async def reset(self, who: str, clear_blocks: bool = False) -> None:
        """Clears the model history, rain and pipe capacities. Municipality blocks are KEPT unless clear_blocks=True."""
        async with self._infer_lock:
            async with self._state_lock:
                self.provider.reset()
                self.pending_rain = 0.0
                self.capacity = None
            if clear_blocks:
                async with self.pool.acquire() as conn:
                    await conn.execute("UPDATE blocks SET released_at = now(), released_by = $1 WHERE released_at IS NULL", who)
        await self.refresh_blocks()
        await self.tick()

    async def refresh_blocks(self) -> None:
        """Re-sync manholes.admin_override from the blocks table, re-price streets now, reload the blocks cache.
        Takes the inference lock itself: callers must NOT already hold it."""
        async with self._infer_lock:                         # never overlaps a tick's street-cost update
            async with self.pool.acquire() as conn:
                async with conn.transaction():
                    await conn.execute(SYNC_OVERRIDES)
                    await conn.execute(FLOOD_PENALTY_UPDATE, self.settings.spatial_join_radius_m,
                                       self.settings.flood_cost_multiplier)
                rows = await conn.fetch("SELECT node_id, source, note, created_at, report_ref, created_by "
                                        "FROM blocks WHERE released_at IS NULL")
        self.blocks = {r["node_id"]: dict(r) for r in rows}

    # pipe capacity (experimental: the current model does not respond reliably to it)
    async def set_capacity(self, updates: dict[int, float], replace: bool) -> int:
        n = self.provider.n_edges
        if n == 0:
            raise ValueError("The active model does not use pipe capacity")
        bad = [e for e in updates if not (0 <= e < n)]
        if bad:
            raise ValueError(f"edge_idx out of range (0..{n - 1}): {bad[:10]}")
        async with self._state_lock:
            w = np.ones(n, dtype=np.float32) if (replace or self.capacity is None) else self.capacity.copy()
            for e, c in updates.items():
                w[e] = c
            self.capacity = None if bool((w >= 1.0).all()) else w
            return int((w < 1.0).sum())

    async def clear_capacity(self) -> None:
        async with self._state_lock:
            self.capacity = None

    # ------------------------------------------------------------------ read helpers
    def age_seconds(self) -> Optional[float]:
        return None if self.snapshot is None else time.time() - self.snapshot.computed_at

    def meta_block(self, hours: float = 0.0) -> dict:
        """The 'freshness' block attached to every data response."""
        s = self.snapshot
        age = self.age_seconds()
        conf = next((h["confidence"] for h in FORECAST_HORIZONS if h["hours"] == hours), "live" if hours == 0 else None)
        return {
            "computedAt": None if s is None else _iso(s.computed_at),
            "ageSeconds": None if age is None else round(age, 1),
            "stale": age is None or age > self.settings.stale_after_seconds,
            "modelSource": self.provider.name,
            "modelVersion": self.provider.version,
            "isMockData": self.provider.name == "mock",
            "rainMmHr": None if s is None else s.rain_mm_hr,
            "horizonHours": hours,
            "confidence": conf,
            "blockageEffective": self.settings.blockage_effective,
        }


def _iso(ts: float) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
