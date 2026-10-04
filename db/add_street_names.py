"""
add_street_names.py -- adds streets.name from the OSM graphml and a precomputed manholes.place_name
(nearest named street). Does NOT truncate anything, so it is safe on the live database.

    python db/add_street_names.py --osm-graphml T_NAGAR_OSM_drive.graphml.xml
"""
import argparse
import asyncio
import os

import asyncpg
import osmnx as ox


def first_name(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else None
    return str(value).strip() if value else None


def osm_key(osmid):
    if isinstance(osmid, (int, str)):
        try:
            return int(osmid)
        except ValueError:
            return None
    return None


async def run(database_url: str, graphml: str) -> None:
    g = ox.convert.to_undirected(ox.load_graphml(graphml))
    names: dict[int, str] = {}
    for _, _, data in g.edges(data=True):
        key, name = osm_key(data.get("osmid")), first_name(data.get("name"))
        if key is not None and name:
            names.setdefault(key, name)
    print(f"{len(names)} named OSM ways found in the graphml.")

    conn = await asyncpg.connect(database_url)
    await conn.execute("ALTER TABLE streets ADD COLUMN IF NOT EXISTS name text")
    await conn.executemany("UPDATE streets SET name = $2 WHERE osm_id = $1", list(names.items()))
    total = await conn.fetchval("SELECT count(*) FROM streets")
    named = await conn.fetchval("SELECT count(*) FROM streets WHERE name IS NOT NULL")
    print(f"streets with a name: {named} / {total}")

    await conn.execute("ALTER TABLE manholes ADD COLUMN IF NOT EXISTS place_name text")
    await conn.execute(
        "UPDATE manholes m SET place_name = (SELECT s.name FROM streets s WHERE s.name IS NOT NULL "
        "ORDER BY s.geom <-> m.geom LIMIT 1)")
    print("manholes.place_name filled. Most common:")
    for r in await conn.fetch("SELECT place_name, count(*) c FROM manholes GROUP BY 1 ORDER BY 2 DESC LIMIT 8"):
        print(f"  {r['place_name']}: {r['c']}")
    await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--osm-graphml", required=True)
    ap.add_argument("--database-url", default=os.getenv("DATABASE_URL", "postgresql://flood:flood@localhost:5433/flood_db"))
    a = ap.parse_args()
    asyncio.run(run(a.database_url, a.osm_graphml))
