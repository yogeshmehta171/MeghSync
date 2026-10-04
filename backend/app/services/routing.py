"""Flood-aware routing. Normal route = shortest path ignoring floods; safe route = same search on flood-penalised costs."""
from __future__ import annotations

import json
from typing import Optional

from ..db import ASTAR_NORMAL, ASTAR_SAFE, NEAREST_VERTEX
from .reports import ReportError


def join_segments(segments: list[list[list[float]]]) -> list[list[float]]:
    """Join street segments into one path. pgRouting may walk a segment backwards, so orient each one."""
    path: list[list[float]] = []
    for seg in segments:
        if not seg:
            continue
        if not path:
            path = [list(p) for p in seg]
            continue
        a, b = seg[0], seg[-1]
        if path[-1] == a:
            path.extend(seg[1:])
        elif path[-1] == b:
            path.extend(reversed(seg[:-1]))
        elif path[0] in (a, b):                              # the first segment had been stored backwards
            path.reverse()
            if path[-1] == a:
                path.extend(seg[1:])
            else:
                path.extend(reversed(seg[:-1]))
        else:
            path.extend(seg)
    return path


def assemble(rows) -> dict:
    segs, length, flooded, pen = [], 0.0, 0.0, 0
    for r in rows:
        if r["edge"] == -1 or r["geom_json"] is None:
            continue
        L = float(r["length_m"])
        length += L
        if r["cost"] is not None and r["cost"] > L * 2:
            pen += 1
            flooded += L
        segs.append(json.loads(r["geom_json"])["coordinates"])
    path = join_segments(segs)
    return {"path": [[p[1], p[0]] for p in path],            # [lat, lng] for Leaflet
            "lengthM": round(length, 1), "floodedLengthM": round(flooded, 1), "penalizedSegments": pen}


def eta_minutes(length_m: float, speed_kmh: float) -> float:
    return round(length_m / (speed_kmh * 1000.0 / 60.0), 1)


async def compute_route(pool, engine, start: tuple[float, float], dest: tuple[float, float]) -> dict:
    """start/dest are (lat, lon)."""
    min_lon, min_lat, max_lon, max_lat = engine.bbox
    for label, (lat, lon) in (("Start", start), ("Destination", dest)):
        if not (min_lon <= lon <= max_lon and min_lat <= lat <= max_lat):
            raise ReportError(422, f"{label} is outside the T. Nagar service area")
    async with pool.acquire() as conn:
        s = await conn.fetchrow(NEAREST_VERTEX, start[1], start[0])
        e = await conn.fetchrow(NEAREST_VERTEX, dest[1], dest[0])
        if s is None or e is None:
            raise ReportError(404, "No routable street found near those points")
        if s["dist_m"] > engine.settings.max_snap_distance_m or e["dist_m"] > engine.settings.max_snap_distance_m:
            raise ReportError(422, "Point is too far from any street in the network")
        if s["id"] == e["id"]:
            raise ReportError(422, "Start and destination are too close")
        safe_rows = await conn.fetch(ASTAR_SAFE, s["id"], e["id"])
        normal_rows = await conn.fetch(ASTAR_NORMAL, s["id"], e["id"])
    safe, normal = assemble(safe_rows), assemble(normal_rows)
    if len(safe["path"]) < 2 or len(normal["path"]) < 2:
        raise ReportError(409, "No path exists between the given points")
    spd = engine.settings.route_speed_kmh
    for r in (safe, normal):
        r["etaMin"] = eta_minutes(r["lengthM"], spd)
    extra_m = max(0.0, round(safe["lengthM"] - normal["lengthM"], 1))
    normal_exposed = normal["floodedLengthM"] > 0
    if safe["floodedLengthM"] > 0:
        msg = "No fully dry route exists right now; the safe route minimises flooded streets."
    elif normal_exposed:
        msg = "Your usual route crosses flooded streets. The safe route avoids them."
    else:
        msg = "No flooding on your route."
    return {
        "safe": safe, "normal": normal,
        "extraM": extra_m, "extraEtaMin": round(max(0.0, safe["etaMin"] - normal["etaMin"]), 1),
        "normalRouteFlooded": normal_exposed, "unavoidableFlood": safe["floodedLengthM"] > 0,
        "message": msg, "meta": engine.meta_block(0.0),
    }


async def log_route(pool, start, dest, result) -> None:
    """Anonymous usage record: coordinates rounded to ~110 m, no identity."""
    try:
        async with pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO route_requests(start_lat,start_lon,end_lat,end_lon,normal_m,safe_m,flood_penalized) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7)", round(start[0], 3), round(start[1], 3), round(dest[0], 3),
                round(dest[1], 3), result["normal"]["lengthM"], result["safe"]["lengthM"], result["normalRouteFlooded"])
    except Exception:
        pass
