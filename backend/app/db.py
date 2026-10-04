"""Connection pool, migration runner, and every SQL statement used by more than one module."""
from __future__ import annotations

import json
from pathlib import Path

import asyncpg

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


async def _init_conn(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def create_pool(dsn: str) -> asyncpg.Pool:
    return await asyncpg.create_pool(dsn, min_size=2, max_size=10, init=_init_conn)


async def run_migrations(pool: asyncpg.Pool) -> list[str]:
    """Apply migrations/*.sql in name order, once each. Returns the names applied now."""
    applied_now = []
    async with pool.acquire() as conn:
        await conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations "
                           "(name text PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())")
        done = {r["name"] for r in await conn.fetch("SELECT name FROM schema_migrations")}
        for f in sorted(MIGRATIONS_DIR.glob("*.sql")):
            if f.name in done:
                continue
            async with conn.transaction():
                await conn.execute(f.read_text(encoding="utf-8"))
                await conn.execute("INSERT INTO schema_migrations(name) VALUES ($1)", f.name)
            applied_now.append(f.name)
    return applied_now


# --------------------------------------------------------------------------- SQL (PostGIS / pgRouting)
UPDATE_MANHOLE_FLOOD = """
UPDATE manholes
SET flood_depth_m = x.depth_m,
    is_flooded = x.depth_m > $2
FROM (SELECT unnest($1::text[]) AS id, unnest($3::double precision[]) AS depth_m) x
WHERE manholes.id = x.id;
"""

# A street is penalised if any flooded OR blocked manhole is within $1 metres. Only rows that change are written.
FLOOD_PENALTY_UPDATE = """
WITH flooded AS (
    SELECT geom::geography AS g FROM manholes WHERE is_flooded = TRUE OR admin_override = TRUE
),
target AS (
    SELECT s.id,
           CASE WHEN EXISTS (SELECT 1 FROM flooded f WHERE ST_DWithin(s.geom::geography, f.g, $1::double precision))
                THEN s.length_m * $2::double precision
                ELSE s.length_m::double precision END AS new_cost
    FROM streets s
)
UPDATE streets s SET cost = t.new_cost, reverse_cost = t.new_cost
FROM target t
WHERE s.id = t.id AND (s.cost IS DISTINCT FROM t.new_cost OR s.reverse_cost IS DISTINCT FROM t.new_cost);
"""

COUNT_PENALIZED = "SELECT count(*) FROM streets WHERE cost > length_m * 2;"
COUNT_ROUTE_BLOCKING = "SELECT count(*) FROM manholes WHERE is_flooded = TRUE;"

SYNC_OVERRIDES = """
UPDATE manholes m
SET admin_override = EXISTS (SELECT 1 FROM blocks b WHERE b.node_id = m.id AND b.released_at IS NULL)
WHERE m.admin_override IS DISTINCT FROM EXISTS (SELECT 1 FROM blocks b WHERE b.node_id = m.id AND b.released_at IS NULL);
"""

LOAD_NODES = """
SELECT m.id, m.idx, COALESCE(m.max_depth_m, 0) AS max_depth_m,
       ST_Y(m.geom) AS lat, ST_X(m.geom) AS lon,
       COALESCE(nm.location, m.place_name) AS location, nm.elevation_m, nm.imperviousness_pct
FROM manholes m LEFT JOIN node_meta nm ON nm.node_id = m.id
ORDER BY m.idx;
"""

NETWORK_BBOX = """
SELECT ST_XMin(e) AS min_lon, ST_YMin(e) AS min_lat, ST_XMax(e) AS max_lon, ST_YMax(e) AS max_lat
FROM (SELECT ST_Extent(geom) AS e FROM streets) x;
"""

NEAREST_NODE = """
SELECT m.id, ST_Distance(m.geom::geography, p.geom::geography) AS dist_m
FROM manholes m, (SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS geom) p
ORDER BY m.geom <-> p.geom LIMIT 1;
"""

NEAREST_VERTEX = """
SELECT v.id, ST_Distance(v.geom::geography, p.geom::geography) AS dist_m
FROM streets_vertices_pgr v, (SELECT ST_SetSRID(ST_MakePoint($1, $2), 4326) AS geom) p
ORDER BY v.geom <-> p.geom LIMIT 1;
"""

_ASTAR_INNER_PENALISED = ("SELECT id, source, target, cost, reverse_cost, "
                          "ST_X(ST_StartPoint(geom)) AS x1, ST_Y(ST_StartPoint(geom)) AS y1, "
                          "ST_X(ST_EndPoint(geom)) AS x2, ST_Y(ST_EndPoint(geom)) AS y2 FROM streets")
_ASTAR_INNER_PLAIN = ("SELECT id, source, target, length_m::float8 AS cost, length_m::float8 AS reverse_cost, "
                      "ST_X(ST_StartPoint(geom)) AS x1, ST_Y(ST_StartPoint(geom)) AS y1, "
                      "ST_X(ST_EndPoint(geom)) AS x2, ST_Y(ST_EndPoint(geom)) AS y2 FROM streets")

ASTAR_SAFE = f"""
SELECT r.seq, r.edge, r.cost, s.length_m, ST_AsGeoJSON(s.geom) AS geom_json
FROM pgr_astar('{_ASTAR_INNER_PENALISED}', $1::bigint, $2::bigint, directed := false) r
LEFT JOIN streets s ON s.id = r.edge ORDER BY r.seq;
"""

# Same search ignoring floods: the "normal" route the citizen would have taken.
ASTAR_NORMAL = f"""
SELECT r.seq, r.edge, s.cost AS cost, s.length_m, ST_AsGeoJSON(s.geom) AS geom_json
FROM pgr_astar('{_ASTAR_INNER_PLAIN}', $1::bigint, $2::bigint, directed := false) r
LEFT JOIN streets s ON s.id = r.edge ORDER BY r.seq;
"""

PIPES_GEOJSON = """
SELECT jsonb_build_object('type', 'FeatureCollection',
  'features', COALESCE(jsonb_agg(jsonb_build_object(
      'type', 'Feature', 'geometry', ST_AsGeoJSON(geom)::jsonb,
      'properties', jsonb_build_object('edge_idx', edge_idx, 'id', id, 'kind', kind, 'blockable', blockable)
  ) ORDER BY edge_idx), '[]'::jsonb))::text AS fc
FROM pipes WHERE geom IS NOT NULL;
"""
