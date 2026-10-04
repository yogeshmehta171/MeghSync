# Database setup (only needed on a NEW machine / empty database)

Your current Docker database already has all of this loaded; skip this file unless you rebuild it.

1. Put the two network files in `data/`:  `data/nodes.csv`, `data/links.csv`  (from the old project's `out/` folder),
   and `T_NAGAR_OSM_drive.graphml.xml` somewhere handy.
2. `docker compose up -d`  (creates tables from `db/init_schema.sql` on first start).
3. In an environment with `asyncpg pandas osmnx shapely geopandas`:
   ```
   set DATABASE_URL=postgresql://flood:YOURPASSWORD@localhost:5433/flood_db
   python db/load_data.py  --nodes-csv data/nodes.csv --osm-graphml path\to\T_NAGAR_OSM_drive.graphml.xml
   python db/load_pipes.py --links-csv data/links.csv
   python db/add_street_names.py --osm-graphml path\to\T_NAGAR_OSM_drive.graphml.xml
   python backend/scripts/load_node_meta.py data/nodes.csv
   ```
Order matters: manholes before pipes (pipe lines are drawn between manholes).
