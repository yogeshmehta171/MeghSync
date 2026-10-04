"""Endpoints open to citizens. Nothing here changes the model or any official data."""
from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException, Query, Request

from ..db import PIPES_GEOJSON
from ..ratelimit import RateLimiter
from ..schemas import ReportCreate, RouteRequest
from ..services import reports as reports_svc
from ..services import routing as routing_svc
from ..services.nodes import VALID_HOURS, build_nodes

router = APIRouter(prefix="/api")
_report_limit = RateLimiter(5, 3600, "report")
_route_limit = RateLimiter(60, 60, "route")


def _eng(request: Request):
    return request.app.state.engine


@router.get("/health")
async def health(request: Request):
    e = _eng(request)
    return {"status": "ok" if e.snapshot else "starting", "modelSource": e.provider.name,
            "isMockData": e.provider.name == "mock", "ageSeconds": e.age_seconds(),
            "stale": e.age_seconds() is None or e.age_seconds() > e.settings.stale_after_seconds}


@router.get("/nodes")
async def nodes(request: Request, hours: float = Query(0.0, description="0, 0.5, 1, 2 or 3")):
    e = _eng(request)
    if hours not in VALID_HOURS:
        raise HTTPException(422, f"hours must be one of {VALID_HOURS}")
    if e.snapshot is None:
        raise HTTPException(503, "No prediction computed yet")
    return {"data": build_nodes(e, hours, admin=False), "meta": e.meta_block(hours)}


@router.get("/pipes")
async def pipes(request: Request):
    async with _eng(request).pool.acquire() as conn:
        fc = await conn.fetchval(PIPES_GEOJSON)
    return json.loads(fc)


@router.post("/route")
async def route(request: Request, req: RouteRequest):
    _route_limit.check(request)
    e = _eng(request)
    a, b = (req.start.lat, req.start.lon), (req.destination.lat, req.destination.lon)
    result = await routing_svc.compute_route(e.pool, e, a, b)
    await routing_svc.log_route(e.pool, a, b, result)
    return result


@router.post("/reports", status_code=201)
async def create_report(request: Request, body: ReportCreate):
    _report_limit.check(request)
    e = _eng(request)
    try:
        phone = reports_svc.validate_phone(body.phone)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    name = reports_svc.clean_text(body.name, 80)
    loc = reports_svc.clean_text(body.location, 200)
    desc = reports_svc.clean_text(body.description, 1000)
    if len(name) < 2 or len(loc) < 3 or len(desc) < 3:
        raise HTTPException(422, "Name, location and description cannot be blank")
    r = await reports_svc.create_report(e.pool, e, name, phone, loc, desc, body.lat, body.lon)
    # Citizens get back only what they need; the matched node is an internal detail.
    return {"id": r["id"], "status": r["status"], "timestamp": r["timestamp"]}


@router.get("/reports/{ref}/status")
async def report_status(request: Request, ref: str):
    if not re.fullmatch(r"R\d{5,10}", ref):
        raise HTTPException(404, "Report not found")
    r = await reports_svc.public_status(_eng(request).pool, ref)
    if r is None:
        raise HTTPException(404, "Report not found")
    return r
