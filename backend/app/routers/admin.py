"""Municipality-only endpoints. EVERY route here requires a valid login (router-level dependency)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ..auth.deps import Official, require_official
from ..schemas import (BlockCreate, ConfigUpdate, MeasuresRequest, PipeCapacityRequest, RainRequest, ResetRequest, ReviewRequest)
from ..services import blocks as blocks_svc
from ..services import reports as reports_svc
from ..services.actions import log_action
from ..services.nodes import VALID_HOURS, build_nodes, overview

router = APIRouter(prefix="/api/admin", dependencies=[Depends(require_official)])


def _eng(request: Request):
    return request.app.state.engine


def _ready(e):
    if e.snapshot is None:
        raise HTTPException(503, "No prediction computed yet")


# ------------------------------------------------------------------ nodes / overview
@router.get("/nodes")
async def nodes(request: Request, hours: float = Query(0.0)):
    e = _eng(request)
    _ready(e)
    if hours not in VALID_HOURS:
        raise HTTPException(422, f"hours must be one of {VALID_HOURS}")
    return {"data": build_nodes(e, hours, admin=True), "meta": e.meta_block(hours)}


@router.get("/nodes/{node_id}")
async def node_detail(request: Request, node_id: str):
    e = _eng(request)
    _ready(e)
    if node_id not in e.node_index:
        raise HTTPException(404, "Unknown node")
    i = e.node_index[node_id]
    node = next(n for n in build_nodes(e, 0.0, admin=True) if n["id"] == node_id)
    node["recent"] = [{"t": round(t, 1), "depthCm": round(float(arr[i]) * 100, 1)} for t, arr in list(e.recent)[-12:]]
    node["pipeDepthM"] = round(float(e.snapshot.depth_m[i]), 2)
    node["maxDepthM"] = round(float(e.max_depth[i]), 2)
    return {"data": node, "meta": e.meta_block(0.0)}


@router.get("/overview")
async def get_overview(request: Request):
    e = _eng(request)
    _ready(e)
    open_alerts = await e.pool.fetchval("SELECT count(*) FROM alerts WHERE resolved_at IS NULL")
    return {"data": {**overview(e), "openAlerts": int(open_alerts)}, "meta": e.meta_block(0.0)}


# ------------------------------------------------------------------ simulation controls
@router.post("/rain")
async def set_rain(request: Request, body: RainRequest, official: Official = Depends(require_official)):
    e = _eng(request)
    await e.set_rain(body.rain_mm_hr)
    # Slider drags send many values: fold them into ONE log row per official per 30 s.
    desc = f"Set rainfall to {body.rain_mm_hr:g} mm/hr"
    async with e.pool.acquire() as conn:
        upd = await conn.fetchval(
            "UPDATE actions SET description=$2, ts=now() WHERE id = (SELECT id FROM actions WHERE action='SET_RAINFALL' "
            "AND official_id=$1 AND ts > now() - interval '30 seconds' ORDER BY id DESC LIMIT 1) RETURNING id",
            official.username, desc)
        if upd is None:
            await log_action(conn, official.username, "SIM", "SET_RAINFALL", desc, "COMPLETED")
    return {"status": "accepted", "rainMmHr": body.rain_mm_hr,
            "nextUpdateInSeconds": e.settings.inference_interval_seconds}


@router.post("/reset")
async def reset(request: Request, body: ResetRequest | None = None, official: Official = Depends(require_official)):
    e = _eng(request)
    clear = bool(body and body.clear_blocks)
    await e.reset(official.username, clear_blocks=clear)
    async with e.pool.acquire() as conn:
        await log_action(conn, official.username, "SIM", "RESET_SIMULATION",
                         "Reset simulation" + (" and released ALL blocks" if clear else " (blocks kept)"), "COMPLETED")
    return {"status": "reset", "blocksCleared": clear}


# ------------------------------------------------------------------ blocks
@router.get("/blocks")
async def get_blocks(request: Request):
    e = _eng(request)
    return {"data": blocks_svc.list_active(e), "meta": e.meta_block(0.0)}


@router.post("/blocks", status_code=201)
async def add_block(request: Request, body: BlockCreate, official: Official = Depends(require_official)):
    e = _eng(request)
    return await blocks_svc.add_manual(e.pool, e, official.username, body.node_id, body.lat, body.lon, body.note)


@router.delete("/blocks/{node_id}")
async def release_block(request: Request, node_id: str, official: Official = Depends(require_official)):
    e = _eng(request)
    return await blocks_svc.release(e.pool, e, official.username, node_id)


# ------------------------------------------------------------------ reports
@router.get("/reports")
async def list_reports(request: Request, status: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=1000)):
    if status and status not in ("PENDING", "APPROVED", "REJECTED", "RESOLVED"):
        raise HTTPException(422, "Invalid status")
    e = _eng(request)
    return {"data": await reports_svc.list_reports(e.pool, status, limit)}


@router.post("/reports/{ref}/approve")
async def approve_report(request: Request, ref: str, body: ReviewRequest | None = None,
                         official: Official = Depends(require_official)):
    e = _eng(request)
    b = body or ReviewRequest()
    return await reports_svc.approve(e.pool, e, ref, b.node_id, official.username, b.note)


@router.post("/reports/{ref}/reject")
async def reject_report(request: Request, ref: str, body: ReviewRequest | None = None,
                        official: Official = Depends(require_official)):
    e = _eng(request)
    return await reports_svc.reject(e.pool, ref, official.username, (body.note if body else None))


@router.post("/reports/{ref}/measures")
async def report_measures(request: Request, ref: str, body: MeasuresRequest, official: Official = Depends(require_official)):
    e = _eng(request)
    return await reports_svc.set_measures(e.pool, ref, body.measures, official.username)


@router.post("/reports/{ref}/resolve")
async def resolve_report(request: Request, ref: str, body: ReviewRequest | None = None,
                         official: Official = Depends(require_official)):
    e = _eng(request)
    return await reports_svc.resolve(e.pool, e, ref, official.username, (body.note if body else None))


# ------------------------------------------------------------------ alerts / logs
@router.get("/alerts")
async def alerts(request: Request, active: bool = Query(True), limit: int = Query(200, ge=1, le=1000)):
    e = _eng(request)
    where = "WHERE resolved_at IS NULL" if active else ""
    rows = await e.pool.fetch(f"SELECT * FROM alerts {where} ORDER BY level_rank DESC, updated_at DESC LIMIT $1", limit)
    return {"data": [{"id": r["id"], "nodeId": r["node_id"], "level": r["level"], "peakLevelRank": r["peak_rank"],
                      "depthM": round(r["depth_m"], 3), "message": r["message"],
                      "openedAt": r["opened_at"].isoformat(), "updatedAt": r["updated_at"].isoformat(),
                      "resolvedAt": r["resolved_at"].isoformat() if r["resolved_at"] else None,
                      "acknowledgedBy": r["acknowledged_by"]} for r in rows],
            "meta": e.meta_block(0.0)}


@router.post("/alerts/{alert_id}/ack")
async def ack_alert(request: Request, alert_id: int, official: Official = Depends(require_official)):
    e = _eng(request)
    async with e.pool.acquire() as conn:
        r = await conn.fetchrow("UPDATE alerts SET acknowledged_by=$2 WHERE id=$1 RETURNING node_id", alert_id, official.username)
        if r is None:
            raise HTTPException(404, "Alert not found")
        await log_action(conn, official.username, r["node_id"], "ACK_ALERT", f"Acknowledged alert {alert_id}", "COMPLETED")
    return {"status": "acknowledged"}


@router.get("/logs")
async def logs(request: Request, status: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=1000)):
    if status and status not in ("PENDING", "COMPLETED", "REJECTED"):
        raise HTTPException(422, "Invalid status")
    e = _eng(request)
    # Report actions also carry the measures currently recorded on that report (LEFT JOIN: other actions get NULL).
    base = ("SELECT a.*, rp.measures AS measures FROM actions a "
            "LEFT JOIN reports rp ON rp.ref = a.ref_id AND a.action LIKE '%REPORT%' ")
    if status:
        rows = await e.pool.fetch(base + "WHERE a.status=$1 ORDER BY a.id DESC LIMIT $2", status, limit)
    else:
        rows = await e.pool.fetch(base + "ORDER BY a.id DESC LIMIT $1", limit)
    return {"data": [{"timestamp": r["ts"].isoformat(), "officialId": r["official_id"], "refId": r["ref_id"],
                      "action": r["action"], "description": r["description"], "status": r["status"],
                      "measures": r["measures"]} for r in rows]}


# ------------------------------------------------------------------ settings
@router.get("/config")
async def get_config(request: Request):
    return {"data": _eng(request).cfg.values}


@router.put("/config")
async def put_config(request: Request, body: ConfigUpdate, official: Official = Depends(require_official)):
    e = _eng(request)
    try:
        values = await e.cfg.update(body.changes, official.username)
    except (ValueError, TypeError) as ex:
        raise HTTPException(422, str(ex))
    async with e.pool.acquire() as conn:
        await log_action(conn, official.username, "CONFIG", "UPDATE_CONFIG",
                         "Changed settings: " + ", ".join(sorted(body.changes)), "COMPLETED")
    return {"data": values}


# ------------------------------------------------------------------ experimental: pipe capacity
@router.get("/blockage")
async def get_pipe_capacity(request: Request):
    e = _eng(request)
    cap = e.capacity
    blocked = [] if cap is None else [{"edge_idx": int(i), "capacity_fraction": float(cap[i])}
                                      for i in (cap < 1.0).nonzero()[0]]
    return {"n_edges": e.provider.n_edges, "blockageEffective": e.settings.blockage_effective, "blocked": blocked}


@router.post("/blockage")
async def set_pipe_capacity(request: Request, body: PipeCapacityRequest, official: Official = Depends(require_official)):
    e = _eng(request)
    try:
        n = await e.set_capacity({b.edge_idx: b.capacity_fraction for b in body.blockages}, body.replace)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    return {"status": "accepted", "blockedEdges": n, "blockageEffective": e.settings.blockage_effective}


@router.delete("/blockage")
async def clear_pipe_capacity(request: Request):
    await _eng(request).clear_capacity()
    return {"status": "cleared"}
