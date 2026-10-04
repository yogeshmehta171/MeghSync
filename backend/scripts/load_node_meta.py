"""
Fill node_meta (street name, elevation, imperviousness) from out/nodes.csv so the dashboard shows real values.

    python scripts/load_node_meta.py ../out/nodes.csv
    python scripts/load_node_meta.py nodes.csv --id-col node_id --location-col street --elevation-col invert_elev --imperv-col imperv

Columns are auto-detected by name; the script PRINTS what it chose and asks you to confirm, because a wrong guess
would put wrong numbers on an official dashboard.
"""
import argparse
import asyncio
import os
import sys

import asyncpg
import pandas as pd


def pick(df, explicit, *hints):
    if explicit:
        return explicit if explicit in df.columns else sys.exit(f"column '{explicit}' not in file: {list(df.columns)}")
    for h in hints:
        for c in df.columns:
            if h in c.lower():
                return c
    return None


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("csv")
    ap.add_argument("--id-col"); ap.add_argument("--location-col")
    ap.add_argument("--elevation-col"); ap.add_argument("--imperv-col")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation question")
    a = ap.parse_args()
    df = pd.read_csv(a.csv)
    cols = {"id": pick(df, a.id_col, "node_id", "id", "name"),
            "location": pick(df, a.location_col, "street", "location", "address", "road"),
            "elevation": pick(df, a.elevation_col, "elev", "ground", "rim"),
            "imperv": pick(df, a.imperv_col, "imperv", "paved")}
    print("File columns:", list(df.columns))
    print("Using:", cols)
    if cols["id"] is None:
        sys.exit("Could not find the node id column; pass --id-col")
    if not a.yes and input("Look right? [y/N] ").strip().lower() != "y":
        sys.exit("Aborted. Re-run with explicit --*-col options.")
    rows = []
    for _, r in df.iterrows():
        def g(k, cast=float):
            c = cols[k]
            if c is None or pd.isna(r[c]):
                return None
            return cast(r[c])
        rows.append((str(r[cols["id"]]), g("location", str), g("elevation"), g("imperv")))
    conn = await asyncpg.connect(os.getenv("DATABASE_URL", "postgresql://flood:flood@localhost:5433/flood_db"))
    try:
        await conn.executemany(
            "INSERT INTO node_meta(node_id, location, elevation_m, imperviousness_pct) VALUES ($1,$2,$3,$4) "
            "ON CONFLICT (node_id) DO UPDATE SET location=EXCLUDED.location, elevation_m=EXCLUDED.elevation_m, "
            "imperviousness_pct=EXCLUDED.imperviousness_pct", rows)
        n = await conn.fetchval("SELECT count(*) FROM node_meta m JOIN manholes h ON h.id = m.node_id")
        print(f"loaded {len(rows)} rows; {n} match manholes.id")
        if n == 0:
            print("WARNING: no ids matched manholes.id -- check --id-col")
    finally:
        await conn.close()


asyncio.run(main())
