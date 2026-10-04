-- Pravaha-X core schema. Idempotent: safe to run more than once.
-- Existing tables from the SWMM load (manholes, streets, streets_vertices_pgr, pipes) are NOT created here.

ALTER TABLE manholes ADD COLUMN IF NOT EXISTS admin_override boolean NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS users (
    id            serial PRIMARY KEY,
    username      text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    role          text NOT NULL DEFAULT 'municipality' CHECK (role IN ('municipality', 'admin')),
    display_name  text,
    active        boolean NOT NULL DEFAULT TRUE,
    created_at    timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);

-- Optional per-node display data (street name, elevation, imperviousness). Filled by scripts/load_node_meta.py.
CREATE TABLE IF NOT EXISTS node_meta (
    node_id           text PRIMARY KEY,
    location          text,
    elevation_m       double precision,
    imperviousness_pct double precision
);

CREATE TABLE IF NOT EXISTS reports (
    id              serial PRIMARY KEY,
    ref             text UNIQUE,
    name            text NOT NULL,
    phone           text NOT NULL,
    location_text   text NOT NULL,
    description     text NOT NULL,
    lat             double precision,
    lon             double precision,
    matched_node_id text,
    status          text NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','RESOLVED')),
    created_at      timestamptz NOT NULL DEFAULT now(),
    reviewed_by     text,
    reviewed_at     timestamptz,
    review_note     text
);
CREATE INDEX IF NOT EXISTS reports_status_idx ON reports (status, created_at DESC);

-- Persistent blocks. Active = released_at IS NULL. These survive "Reset simulation".
CREATE TABLE IF NOT EXISTS blocks (
    id           serial PRIMARY KEY,
    node_id      text NOT NULL,
    source       text NOT NULL CHECK (source IN ('manual', 'report')),
    report_ref   text,
    created_by   text NOT NULL,
    note         text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    released_at  timestamptz,
    released_by  text
);
CREATE UNIQUE INDEX IF NOT EXISTS blocks_one_active_per_node ON blocks (node_id) WHERE released_at IS NULL;

-- Official action log (the "Logs" page).
CREATE TABLE IF NOT EXISTS actions (
    id          bigserial PRIMARY KEY,
    ts          timestamptz NOT NULL DEFAULT now(),
    official_id text NOT NULL,
    ref_id      text NOT NULL DEFAULT '-',
    action      text NOT NULL,
    description text NOT NULL,
    status      text CHECK (status IN ('PENDING', 'COMPLETED', 'REJECTED'))
);
CREATE INDEX IF NOT EXISTS actions_ts_idx ON actions (ts DESC);

-- Automatic alerts. One OPEN alert (resolved_at IS NULL) per node at most.
CREATE TABLE IF NOT EXISTS alerts (
    id           bigserial PRIMARY KEY,
    node_id      text NOT NULL,
    level        text NOT NULL,
    level_rank   smallint NOT NULL,
    peak_rank    smallint NOT NULL,
    depth_m      double precision NOT NULL,
    message      text NOT NULL,
    opened_at    timestamptz NOT NULL DEFAULT now(),
    updated_at   timestamptz NOT NULL DEFAULT now(),
    resolved_at  timestamptz,
    acknowledged_by text
);
CREATE UNIQUE INDEX IF NOT EXISTS alerts_one_open_per_node ON alerts (node_id) WHERE resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS alerts_opened_idx ON alerts (opened_at DESC);

-- History of predictions, SAMPLED (not every tick) and only for wet nodes, then deleted by the retention job.
CREATE TABLE IF NOT EXISTS prediction_snapshots (
    id              bigserial PRIMARY KEY,
    ts              timestamptz NOT NULL DEFAULT now(),
    horizon_min     integer NOT NULL,
    rain_mm_hr      double precision NOT NULL,
    max_flood_m     double precision NOT NULL,
    wet_nodes       integer NOT NULL,
    blocking_nodes  integer NOT NULL,
    model           text NOT NULL
);
CREATE INDEX IF NOT EXISTS prediction_snapshots_ts_idx ON prediction_snapshots (ts DESC);

CREATE TABLE IF NOT EXISTS node_predictions (
    ts          timestamptz NOT NULL,
    horizon_min integer NOT NULL,
    node_id     text NOT NULL,
    flood_m     real NOT NULL
);
CREATE INDEX IF NOT EXISTS node_predictions_ts_idx ON node_predictions (ts DESC);
CREATE INDEX IF NOT EXISTS node_predictions_node_idx ON node_predictions (node_id, ts DESC);

-- Anonymous route usage (no personal data: coordinates rounded to ~110 m).
CREATE TABLE IF NOT EXISTS route_requests (
    id            bigserial PRIMARY KEY,
    ts            timestamptz NOT NULL DEFAULT now(),
    start_lat     real, start_lon real, end_lat real, end_lon real,
    normal_m      real, safe_m real, flood_penalized boolean
);

-- Runtime settings editable by officials (thresholds, retention).
CREATE TABLE IF NOT EXISTS app_config (
    key        text PRIMARY KEY,
    value      jsonb NOT NULL,
    updated_by text,
    updated_at timestamptz NOT NULL DEFAULT now()
);
