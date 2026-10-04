-- T. Nagar flood nowcasting -- PostGIS + pgRouting base schema (unchanged from the old project).
-- Pravaha-X tables (users, reports, blocks, alerts, ...) are NOT here: the backend creates them
-- itself from backend/migrations/*.sql on startup.

CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgrouting;

CREATE TABLE IF NOT EXISTS manholes (
    id              TEXT PRIMARY KEY,          -- e.g. "D0187"
    idx             INTEGER UNIQUE NOT NULL,   -- row position in nodes.csv; must match the model's node order
    max_depth_m     DOUBLE PRECISION,
    is_flooded      BOOLEAN NOT NULL DEFAULT FALSE,
    flood_depth_m   DOUBLE PRECISION NOT NULL DEFAULT 0,
    geom            GEOMETRY(Point, 4326) NOT NULL
);
CREATE INDEX IF NOT EXISTS manholes_geom_gix ON manholes USING GIST (geom);
CREATE INDEX IF NOT EXISTS manholes_flooded_idx ON manholes (is_flooded) WHERE is_flooded;

CREATE TABLE IF NOT EXISTS streets (
    id              BIGSERIAL PRIMARY KEY,
    osm_id          BIGINT,
    source          BIGINT,
    target          BIGINT,
    geom            GEOMETRY(LineString, 4326) NOT NULL,
    length_m        DOUBLE PRECISION NOT NULL,
    cost            DOUBLE PRECISION,
    reverse_cost    DOUBLE PRECISION
);

CREATE OR REPLACE FUNCTION streets_default_cost() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.cost IS NULL THEN NEW.cost := NEW.length_m; END IF;
    IF NEW.reverse_cost IS NULL THEN NEW.reverse_cost := NEW.length_m; END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_streets_default_cost ON streets;
CREATE TRIGGER trg_streets_default_cost BEFORE INSERT ON streets
    FOR EACH ROW EXECUTE FUNCTION streets_default_cost();

CREATE INDEX IF NOT EXISTS streets_geom_gix ON streets USING GIST (geom);
CREATE INDEX IF NOT EXISTS streets_source_idx ON streets (source);
CREATE INDEX IF NOT EXISTS streets_target_idx ON streets (target);
-- source/target + streets_vertices_pgr are built by db/load_data.py (pgr_extractVertices; pgr_createTopology is gone in pgRouting 4.0).
