"""
load_pipes.py -- builds the `pipes` table (drain links drawn as lines between manholes). Run AFTER load_data.py.

    python db/load_pipes.py --links-csv data/links.csv
"""
import argparse
import asyncio
import os

import asyncpg
import pandas as pd

DEFAULT_URL = os.getenv("DATABASE_URL", "postgresql://flood:flood@localhost:5433/flood_db")


async def main(url: str, links_csv: str) -> None:
    conn = await asyncpg.connect(url)
    await conn.execute("DROP TABLE IF EXISTS pipes;")
    await conn.execute("""
        CREATE TABLE pipes (
            edge_idx INT PRIMARY KEY, id TEXT, kind TEXT, blockable BOOLEAN,
            frm TEXT, to_node TEXT, geom Geometry(LineString, 4326)
        );""")
    df = pd.read_csv(links_csv)
    rows = []
    for idx, row in df.iterrows():   # edge_idx = row order of links.csv (must equal the model's edge order)
        blockable = bool(str(row["id"]).startswith(("P", "V", "X")))
        rows.append((int(idx), str(row["id"]), str(row["kind"]), blockable, str(row["frm"]), str(row["to"])))
    await conn.executemany(
        "INSERT INTO pipes (edge_idx, id, kind, blockable, frm, to_node) VALUES ($1,$2,$3,$4,$5,$6)", rows)
    await conn.execute("""
        UPDATE pipes p SET geom = ST_MakeLine(m1.geom, m2.geom)
        FROM manholes m1, manholes m2 WHERE p.frm = m1.id AND p.to_node = m2.id;""")
    await conn.execute("CREATE INDEX pipes_geom_idx ON pipes USING GIST (geom);")
    n = await conn.fetchval("SELECT count(*) FROM pipes")
    nog = await conn.fetchval("SELECT count(*) FROM pipes WHERE geom IS NULL")
    print(f"Loaded {n} pipes ({nog} without geometry).")
    await conn.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--links-csv", default="data/links.csv")
    ap.add_argument("--database-url", default=DEFAULT_URL)
    a = ap.parse_args()
    asyncio.run(main(a.database_url, a.links_csv))
