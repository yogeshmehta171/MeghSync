"""
load_data.py -- one-time ETL: populates manholes + streets, then builds pgRouting topology.
Offline tool (not part of the running server).

    set DATABASE_URL=postgresql://flood:PASSWORD@localhost:5433/flood_db
    python db/load_data.py --nodes-csv data/nodes.csv --osm-graphml T_NAGAR_OSM_drive.graphml.xml
"""
import argparse
import asyncio
import os

import asyncpg
import osmnx as ox
import pandas as pd
from shapely.geometry import LineString

DEFAULT_URL = os.getenv("DATABASE_URL", "postgresql://flood:flood@localhost:5433/flood_db")


async def load(database_url: str, nodes_csv: str, osm_graphml: str) -> None:
    conn = await asyncpg.connect(database_url)

    # ---- manholes: idx = row order of nodes.csv (must equal the model's node order) ----
    nodes = pd.read_csv(nodes_csv)
    await conn.execute("TRUNCATE manholes CASCADE")
    await conn.executemany(
        "INSERT INTO manholes (id, idx, max_depth_m, geom) "
        "VALUES ($1, $2, $3, ST_SetSRID(ST_MakePoint($4, $5), 4326))",
        [(row.id, i, float(getattr(row, "max_depth_m", 0.0) or 0.0), float(row.lon), float(row.lat))
         for i, row in enumerate(nodes.itertuples())],
    )
    print(f"Loaded {len(nodes)} manholes.")

    # ---- streets (OSM road network, what /api/route runs over) ----
    g = ox.load_graphml(osm_graphml)
    g_undirected = ox.convert.to_undirected(g)

    await conn.execute("TRUNCATE streets CASCADE")
    rows = []
    for u, v, data in g_undirected.edges(data=True):
        geom = data.get("geometry")
        if geom is None:
            uy, ux = g_undirected.nodes[u]["y"], g_undirected.nodes[u]["x"]
            vy, vx = g_undirected.nodes[v]["y"], g_undirected.nodes[v]["x"]
            geom = LineString([(ux, uy), (vx, vy)])
        rows.append((data.get("osmid"), geom.wkt, float(data.get("length", geom.length))))

    await conn.executemany(
        "INSERT INTO streets (osm_id, geom, length_m) VALUES ($1, ST_SetSRID(ST_GeomFromText($2), 4326), $3)",
        [(int(osmid) if isinstance(osmid, (int, str)) else None, wkt, length_m) for osmid, wkt, length_m in rows],
    )
    print(f"Loaded {len(rows)} street segments.")

    # ---- topology (pgr_createTopology is removed in pgRouting 4.0, so pgr_extractVertices is used) ----
    await conn.execute(
        """
        DROP TABLE IF EXISTS streets_vertices_pgr;
        SELECT id, in_edges, out_edges, x, y, geom
        INTO streets_vertices_pgr
        FROM pgr_extractVertices('SELECT id, geom FROM streets ORDER BY id');
        CREATE INDEX ON streets_vertices_pgr USING GIST (geom);
        UPDATE streets AS e SET source = v.id FROM streets_vertices_pgr AS v WHERE ST_StartPoint(e.geom) = v.geom;
        UPDATE streets AS e SET target = v.id FROM streets_vertices_pgr AS v WHERE ST_EndPoint(e.geom) = v.geom;
        """
    )
    print("Topology built.")
    await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes-csv", default="data/nodes.csv")
    ap.add_argument("--osm-graphml", required=True)
    ap.add_argument("--database-url", default=DEFAULT_URL)
    a = ap.parse_args()
    asyncio.run(load(a.database_url, a.nodes_csv, a.osm_graphml))
