"""Manual node blocks made directly on the map by an official. Report-approved blocks live in reports.py."""
from __future__ import annotations

from typing import Optional

from ..db import NEAREST_NODE
from .actions import log_action
from .reports import ReportError

MAX_MANUAL_MATCH_M = 250.0


async def add_manual(pool, engine, official: str, node_id: Optional[str], lat: Optional[float],
                     lon: Optional[float], note: Optional[str]) -> dict:
    async with pool.acquire() as conn:
        if node_id is None:
            if lat is None or lon is None:
                raise ReportError(422, "Provide node_id or lat/lon")
            row = await conn.fetchrow(NEAREST_NODE, lon, lat)
            if row is None or row["dist_m"] > MAX_MANUAL_MATCH_M:
                raise ReportError(422, "No drainage node within 250 m of that point")
            node_id = row["id"]
        if node_id not in engine.node_index:
            raise ReportError(422, f"Unknown node '{node_id}'")
        async with conn.transaction():
            created = await conn.fetchval(
                "INSERT INTO blocks(node_id, source, created_by, note) VALUES ($1,'manual',$2,$3) "
                "ON CONFLICT (node_id) WHERE released_at IS NULL DO NOTHING RETURNING id", node_id, official, note)
            if created is None:
                raise ReportError(409, f"Node {node_id} is already blocked")
            await log_action(conn, official, node_id, "BLOCK_NODE", f"Manually blocked node {node_id}", "COMPLETED")
    await engine.refresh_blocks()
    return {"nodeId": node_id, "source": "manual"}


async def release(pool, engine, official: str, node_id: str) -> dict:
    async with pool.acquire() as conn:
        async with conn.transaction():
            rows = await conn.fetch(
                "UPDATE blocks SET released_at=now(), released_by=$2 WHERE node_id=$1 AND released_at IS NULL "
                "RETURNING report_ref", node_id, official)
            if not rows:
                raise ReportError(404, f"Node {node_id} has no active block")
            for r in rows:                                   # a report-made block released by hand closes its report
                if r["report_ref"]:
                    await conn.execute("UPDATE reports SET status='RESOLVED', reviewed_by=$2, reviewed_at=now() "
                                       "WHERE ref=$1 AND status='APPROVED'", r["report_ref"], official)
            await log_action(conn, official, node_id, "UNBLOCK_NODE", f"Released block on node {node_id}", "COMPLETED")
    await engine.refresh_blocks()
    return {"nodeId": node_id, "released": True}


def list_active(engine) -> list[dict]:
    return [{"nodeId": nid, "source": b["source"], "note": b["note"], "reportRef": b["report_ref"],
             "createdBy": b["created_by"], "createdAt": b["created_at"].isoformat()}
            for nid, b in sorted(engine.blocks.items())]
