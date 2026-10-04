"""Builds the node list the frontend shows. Pure in-memory work: polling endpoints never touch the database."""
from __future__ import annotations

from typing import Optional

from ..model.base import FORECAST_HORIZONS
from .risk import RISK_LABEL, frontend_status, level_for_depth, node_state, suggested_action

HOURS_TO_STEPS = {h["hours"]: h["steps"] for h in FORECAST_HORIZONS}
VALID_HOURS = [0.0] + sorted(HOURS_TO_STEPS)


def flood_array(engine, hours: float):
    snap = engine.snapshot
    if snap is None:
        raise LookupError("No prediction computed yet")
    if hours == 0:
        return snap.flood_m
    if hours not in HOURS_TO_STEPS:
        raise ValueError(f"hours must be one of {VALID_HOURS}")
    return snap.forecasts[HOURS_TO_STEPS[hours]]


def build_nodes(engine, hours: float = 0.0, admin: bool = False) -> list[dict]:
    flood = flood_array(engine, hours)
    snap = engine.snapshot
    th = engine.cfg.thresholds
    out = []
    for i, nid in enumerate(engine.node_ids):
        f = float(flood[i])
        level = level_for_depth(f, th)
        blk = engine.blocks.get(nid)
        state = node_state(f, float(snap.depth_m[i]), float(engine.max_depth[i]), th)
        status = "FLOODED" if blk else frontend_status(state)
        m = engine.meta[i]
        node = {
            "id": nid,
            "location": m["location"] or "T. Nagar",
            "coordinates": [float(engine.lat[i]), float(engine.lon[i])],     # [lat, lng] like the frontend type
            "depth": round(f, 3),                                            # metres
            "risk": RISK_LABEL["CRITICAL" if blk else level],
            "status": status,
            "state": "SURFACE_FLOODING" if blk and state in ("NORMAL", "INCREASED_LEVEL", "SURCHARGE") else state,
            "alertLevel": "CRITICAL" if blk else level,
            "blocked": blk is not None,
            "elevation": m["elevation_m"],
            "imperviousness": m["imperviousness_pct"],
            "suggestedAction": "",
        }
        if admin:
            node["suggestedAction"] = suggested_action(level, state, blk is not None)
            node["blockSource"] = None if blk is None else blk["source"]
            node["predicted"] = {str(h): round(float(engine.snapshot.forecasts[s][i]), 3)
                                 for h, s in HOURS_TO_STEPS.items()}
        out.append(node)
    return out


def overview(engine) -> dict:
    snap = engine.snapshot
    th = engine.cfg.thresholds
    counts = {k: 0 for k in ("SAFE", "LOW", "MODERATE", "HIGH", "CRITICAL")}
    for f in snap.flood_m:
        counts[level_for_depth(float(f), th)] += 1
    horizons = []
    for h in FORECAST_HORIZONS:
        arr = snap.forecasts[h["steps"]]
        horizons.append({"label": h["label"], "hours": h["hours"], "confidence": h["confidence"],
                         "maxFloodM": round(float(arr.max()), 3),
                         "routeBlockingNodes": int((arr >= th["route_block_m"]).sum())})
    return {
        "nodes": len(engine.node_ids),
        "levelCounts": counts,
        "maxFloodM": round(float(snap.flood_m.max()), 3),
        "floodedNodes": int((snap.flood_m >= th["low_m"]).sum()),
        "routeBlockingNodes": snap.route_blocking_count,
        "penalizedStreets": snap.penalized_streets,
        "blockedNodes": len(engine.blocks),
        "blockedByReport": sum(1 for b in engine.blocks.values() if b["source"] == "report"),
        "forecast": horizons,
        "forecastComputeMs": snap.forecast_ms,
    }
