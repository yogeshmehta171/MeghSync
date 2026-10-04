-- Speeds up the 75 m flood-penalty join and nearest-node lookups. IF NOT EXISTS keeps it safe to re-run.
CREATE INDEX IF NOT EXISTS manholes_geom_gix  ON manholes USING GIST (geom);
CREATE INDEX IF NOT EXISTS manholes_geog_gix  ON manholes USING GIST ((geom::geography));
CREATE INDEX IF NOT EXISTS streets_geog_gix   ON streets  USING GIST ((geom::geography));
