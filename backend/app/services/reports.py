"""Citizen reports: validation, node matching, approve / reject / resolve."""
from __future__ import annotations

import re
from typing import Optional

from ..db import NEAREST_NODE
from .actions import log_action

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PHONE_OK = re.compile(r"^\+?[0-9][0-9 \-()]{5,19}$")
MAX_MATCH_DISTANCE_M = 150.0


def clean_text(s: str, max_len: int) -> str:
    return _CONTROL.sub("", s).strip()[:max_len]


def validate_phone(phone: str) -> str:
    p = clean_text(phone, 20)
    digits = re.sub(r"\D", "", p)
    if not _PHONE_OK.match(p) or not (7 <= len(digits) <= 15):
        raise ValueError("Enter a valid phone number (7-15 digits)")
    return p


def match_node_from_text(text: str, node_index: dict[str, int]) -> Optional[str]:
    """If the citizen wrote a node id ('near Node N104'), use it. Case-insensitive, exact token match."""
    upper = {k.upper(): k for k in node_index}
    for tok in re.findall(r"[A-Za-z0-9_\-]+", text):
        if tok.upper() in upper:
            return upper[tok.upper()]
    return None


async def match_node(conn, engine, lat: Optional[float], lon: Optional[float], text: str) -> Optional[str]:
    if lat is not None and lon is not None:
        min_lon, min_lat, max_lon, max_lat = engine.bbox
        if min_lon <= lon <= max_lon and min_lat <= lat <= max_lat:
            row = await conn.fetchrow(NEAREST_NODE, lon, lat)
            if row and row["dist_m"] <= MAX_MATCH_DISTANCE_M:
                return row["id"]
    return match_node_from_text(text, engine.node_index)


def _row(r) -> dict:
    return {
        "id": r["ref"], "name": r["name"], "phone": r["phone"], "location": r["location_text"],
        "description": r["description"], "status": r["status"], "timestamp": r["created_at"].isoformat(),
        "lat": r["lat"], "lon": r["lon"], "matchedNodeId": r["matched_node_id"],
        "reviewedBy": r["reviewed_by"], "reviewedAt": r["reviewed_at"].isoformat() if r["reviewed_at"] else None,
        "reviewNote": r["review_note"],
        "measures": r["measures"], "measuresBy": r["measures_by"],
        "measuresAt": r["measures_at"].isoformat() if r["measures_at"] else None,
    }


async def create_report(pool, engine, name, phone, location, description, lat, lon) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            node = await match_node(conn, engine, lat, lon, location)
            rid = await conn.fetchval(
                "INSERT INTO reports(name, phone, location_text, description, lat, lon, matched_node_id) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id", name, phone, location, description, lat, lon, node)
            ref = f"R{rid:05d}"
            r = await conn.fetchrow("UPDATE reports SET ref = $2 WHERE id = $1 RETURNING *", rid, ref)
    return _row(r)


async def list_reports(pool, status: Optional[str], limit: int) -> list[dict]:
    async with pool.acquire() as conn:
        if status:
            rows = await conn.fetch("SELECT * FROM reports WHERE status = $1 ORDER BY created_at DESC LIMIT $2", status, limit)
        else:
            rows = await conn.fetch("SELECT * FROM reports ORDER BY created_at DESC LIMIT $1", limit)
    return [_row(r) for r in rows]


async def public_status(pool, ref: str) -> Optional[dict]:
    async with pool.acquire() as conn:
        r = await conn.fetchrow("SELECT ref, status, created_at FROM reports WHERE ref = $1", ref)
    return None if r is None else {"id": r["ref"], "status": r["status"], "timestamp": r["created_at"].isoformat()}


class ReportError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code, self.detail = status_code, detail


async def approve(pool, engine, ref: str, node_id: Optional[str], official: str, note: Optional[str]) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT * FROM reports WHERE ref = $1 FOR UPDATE", ref)
            if r is None:
                raise ReportError(404, "Report not found")
            if r["status"] != "PENDING":
                raise ReportError(409, f"Report is already {r['status']}")
            node = node_id or r["matched_node_id"]
            if not node:
                raise ReportError(422, "No node could be matched automatically; choose a node_id")
            if node not in engine.node_index:
                raise ReportError(422, f"Unknown node '{node}'")
            await conn.execute(
                "INSERT INTO blocks(node_id, source, report_ref, created_by, note) VALUES ($1,'report',$2,$3,$4) "
                "ON CONFLICT (node_id) WHERE released_at IS NULL DO NOTHING", node, ref, official, note)
            r = await conn.fetchrow(
                "UPDATE reports SET status='APPROVED', matched_node_id=$2, reviewed_by=$3, reviewed_at=now(), "
                "review_note=$4 WHERE ref=$1 RETURNING *", ref, node, official, note)
            await log_action(conn, official, ref, "APPROVE_REPORT", f"Approved report {ref} and blocked node {node}", "COMPLETED")
    await engine.refresh_blocks()
    return _row(r)


async def set_measures(pool, ref: str, measures: str, official: str) -> dict:
    """Record (or clear) the measures taken for a report. Allowed in any status; every change is logged."""
    text = clean_text(measures, 1000)
    async with pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT ref FROM reports WHERE ref = $1 FOR UPDATE", ref)
            if r is None:
                raise ReportError(404, "Report not found")
            r = await conn.fetchrow(
                "UPDATE reports SET measures=$2, measures_by=$3, measures_at=now() WHERE ref=$1 RETURNING *",
                ref, text or None, official)
            desc = (f"Recorded measures for report {ref}: {text}" if text else f"Cleared measures for report {ref}")
            await log_action(conn, official, ref, "UPDATE_REPORT_MEASURES", desc, "COMPLETED")
    return _row(r)


async def reject(pool, ref: str, official: str, note: Optional[str]) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT status FROM reports WHERE ref = $1 FOR UPDATE", ref)
            if r is None:
                raise ReportError(404, "Report not found")
            if r["status"] != "PENDING":
                raise ReportError(409, f"Report is already {r['status']}")
            r = await conn.fetchrow(
                "UPDATE reports SET status='REJECTED', reviewed_by=$2, reviewed_at=now(), review_note=$3 "
                "WHERE ref=$1 RETURNING *", ref, official, note)
            await log_action(conn, official, ref, "REJECT_REPORT", f"Rejected report {ref}", "REJECTED")
    return _row(r)


async def resolve(pool, engine, ref: str, official: str, note: Optional[str]) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            r = await conn.fetchrow("SELECT status FROM reports WHERE ref = $1 FOR UPDATE", ref)
            if r is None:
                raise ReportError(404, "Report not found")
            if r["status"] != "APPROVED":
                raise ReportError(409, "Only APPROVED reports can be resolved")
            await conn.execute("UPDATE blocks SET released_at=now(), released_by=$2 "
                               "WHERE report_ref=$1 AND released_at IS NULL", ref, official)
            r = await conn.fetchrow("UPDATE reports SET status='RESOLVED', reviewed_by=$2, reviewed_at=now(), "
                                    "review_note=COALESCE($3, review_note) WHERE ref=$1 RETURNING *", ref, official, note)
            await log_action(conn, official, ref, "RESOLVE_REPORT", f"Resolved report {ref}; block released", "COMPLETED")
    await engine.refresh_blocks()
    return _row(r)
