# API reference

This is the contract between the frontend and the backend, written from the code in `backend/app/routers/`. Interactive documentation of the same endpoints is served by the running backend at `http://localhost:8000/docs`.

## Conventions

* **Base URL:** `http://localhost:8000` (the frontend reads `VITE_API_URL`).
* **Format:** JSON in and out. Errors look like `{"detail": "message"}`.
* **Authentication:** `/api/admin/*` needs the header `Authorization: Bearer <token>`. Get the token from `POST /api/auth/login`. Tokens expire after `JWT_TTL_MINUTES` (default 480).
* **Coordinates:** `[lat, lng]` pairs in responses (the order Leaflet expects); request bodies use `{ "lat": ..., "lon": ... }`.
* **Depths** are in metres. **Distances** in metres. **Times** are ISO 8601.
* **Freshness block:** every data response has a `meta` object (below), so a client can tell how old a prediction is.
* **Rate limits** (per client address): login 10 per minute, route 60 per minute, new reports 5 per hour. Over the limit returns `429`.
* **Status codes:** `200` ok, `201` created, `401` not logged in or wrong password, `404` unknown id, `409` conflict (for example a report that was already decided, or no path between two points), `422` invalid input, `429` rate limited, `503` no prediction computed yet.

### The `meta` block

| Field | Meaning |
|---|---|
| `computedAt` | when the current prediction was computed |
| `ageSeconds` | age of that prediction |
| `stale` | true when older than `STALE_AFTER_SECONDS` (default 30) |
| `modelSource` | `gnn` or `mock` |
| `modelVersion` | for example `astgcn-v2:best_model_v3.pt` (the part after the colon is the model file name) |
| `isMockData` | true when the mock provider is in use |
| `rainMmHr` | the rainfall input currently applied |
| `horizonHours` | the horizon this response is for (0, 0.5, 1, 2 or 3) |
| `confidence` | `live`, `moderate`, `low` or `trend_only` (fixed labels in `backend/app/model/base.py`; they were set for the first model and are conservative for the fine-tuned one) |
| `blockageEffective` | whether pipe-capacity blockage is fed to the model (off by default) |

## Public endpoints (no login)

### `GET /api/health`
Returns `{ "status": "ok" | "starting", "modelSource", "isMockData", "ageSeconds", "stale" }`.

### `GET /api/nodes?hours=0`
Predicted state of every node. `hours` must be `0`, `0.5`, `1`, `2` or `3`, otherwise `422`. Returns `503` until the first prediction exists.

```json
{
  "data": [{
    "id": "D0124", "location": "Usman Road", "coordinates": [13.0412, 80.2331],
    "depth": 0.214, "risk": "Moderate", "status": "FLOODED", "state": "SURFACE_FLOODING",
    "alertLevel": "MODERATE", "blocked": false,
    "elevation": 6.1, "imperviousness": 85, "suggestedAction": ""
  }],
  "meta": { "...": "see above" }
}
```

* `depth` is the surface flood depth at the chosen horizon.
* `risk` is one of Safe, Low, Moderate, High, Critical (thresholds in Settings below).
* A node blocked by an official is reported as `status: "FLOODED"`, `risk: "Critical"` so that the map and routing treat it as impassable.

### `GET /api/pipes`
GeoJSON `FeatureCollection` of the drainage links, for drawing the network.

### `POST /api/route`
Request: `{ "start": { "lat": 13.04, "lon": 80.23 }, "destination": { "lat": 13.05, "lon": 80.24 } }`

Both points must lie inside the T. Nagar service area and within 250 m of a street, and must not be the same junction, otherwise `422`. Response:

```json
{
  "normal": { "path": [[13.04, 80.23], "..."], "lengthM": 3636.0, "floodedLengthM": 210.5, "penalizedSegments": 4, "etaMin": 10.9 },
  "safe":   { "path": [[13.04, 80.23], "..."], "lengthM": 3920.0, "floodedLengthM": 0.0,   "penalizedSegments": 0, "etaMin": 11.8 },
  "extraM": 284.0, "extraEtaMin": 0.9,
  "normalRouteFlooded": true, "unavoidableFlood": false,
  "message": "Your usual route crosses flooded streets. The safe route avoids them.",
  "meta": { "...": "..." }
}
```

* `normal` is the shortest route by length. `safe` is the cheapest route when streets near flooded nodes cost 10,000 times more.
* `unavoidableFlood: true` means even the safe route crosses flooded streets, because no dry route exists.
* `etaMin` assumes `ROUTE_SPEED_KMH` (default 20).
* Each request is stored anonymously (coordinates rounded to about 110 m).

### `POST /api/reports`  (201)
A citizen flood report.

| Field | Rules |
|---|---|
| `name` | 2 to 80 characters |
| `phone` | validated phone number, 7 to 20 characters |
| `location` | 3 to 200 characters (free text) |
| `description` | 3 to 1000 characters |
| `lat`, `lon` | optional map pin |

Response: `{ "id": "R00002", "status": "PENDING", "timestamp": "..." }`. If a pin was given and a node lies within 150 m, the server matches it automatically (not shown to the citizen).

### `GET /api/reports/{ref}/status`
`ref` looks like `R00002`. Returns `{ "id", "status", "timestamp" }` or `404`. Citizens get nothing else.

## Authentication

### `POST /api/auth/login`
Request: `{ "municipality_id": "MUNI_ADMIN", "password": "..." }`. Returns `401 "Invalid ID or password"` when wrong.

```json
{ "token": "...", "tokenType": "bearer", "expiresInSeconds": 28800,
  "user": { "id": 1, "username": "MUNI_ADMIN", "displayName": "...", "role": "admin" } }
```

### `GET /api/auth/me`
Returns `{ "id", "username", "role" }` for the current token.

## Admin endpoints (`/api/admin`, login required)

### Predictions and simulation

| Endpoint | Purpose |
|---|---|
| `GET /nodes?hours=0` | Same as the public list, plus `blockSource` (null, `manual` or `report`), `suggestedAction`, and `predicted` (depth for each horizon) |
| `GET /nodes/{node_id}` | One node with `recent` (last 12 depths in cm), `pipeDepthM`, `maxDepthM`. `404` for an unknown id |
| `GET /overview` | City summary (below) |
| `POST /rain` | Body `{ "rain_mm_hr": 0 to 500 }`. Sets the rainfall input. Returns `{ "status": "accepted", "rainMmHr", "nextUpdateInSeconds" }`. Slider drags are folded into one log row per official per 30 seconds |
| `POST /reset` | Body `{ "clear_blocks": false }`. Resets rain, model memory and pipe capacities to dry. Blocks are kept unless `clear_blocks` is true. Returns `{ "status": "reset", "blocksCleared" }` |

`GET /overview` returns `nodes`, `levelCounts` (SAFE, LOW, MODERATE, HIGH, CRITICAL), `maxFloodM`, `floodedNodes`, `routeBlockingNodes`, `penalizedStreets`, `blockedNodes`, `blockedByReport`, `forecast` (one entry per horizon with `label`, `hours`, `confidence`, `maxFloodM`, `routeBlockingNodes`) and `forecastComputeMs`.

### Blocked nodes

| Endpoint | Purpose |
|---|---|
| `GET /blocks` | Active blocks: `nodeId`, `source` (`manual` or `report`), `note`, `reportRef`, `createdBy`, `createdAt` |
| `POST /blocks` (201) | Body `{ "node_id": "D0348", "note": "..." }` or `{ "lat", "lon", "note" }` (the nearest node is used). Returns `{ "nodeId", "source": "manual" }` |
| `DELETE /blocks/{node_id}` | Releases a block. Returns `{ "nodeId", "released": true }` |

Blocks are stored in the database and survive restarts and simulation resets.

### Citizen reports

Statuses: `PENDING`, `APPROVED`, `REJECTED`, `RESOLVED`.

| Endpoint | Purpose |
|---|---|
| `GET /reports?status=&limit=200` | All reports, newest first |
| `POST /reports/{ref}/approve` | Body `{ "node_id": "...", "note": "..." }` (both optional). The official's `node_id` is the node that gets blocked. Without it the automatic match is used, and with neither the call fails with `422`. An already decided report returns `409` |
| `POST /reports/{ref}/reject` | Body `{ "note": "..." }` (optional) |
| `POST /reports/{ref}/measures` | Body `{ "measures": "text, up to 1000 characters" }`. Records what was done. An empty string clears it. Allowed in any status |
| `POST /reports/{ref}/resolve` | Marks an approved report resolved and releases its block |

A report row has: `id`, `name`, `phone`, `location`, `description`, `status`, `timestamp`, `lat`, `lon`, `matchedNodeId`, `reviewedBy`, `reviewedAt`, `reviewNote`, `measures`, `measuresBy`, `measuresAt`.

### Alerts

| Endpoint | Purpose |
|---|---|
| `GET /alerts?active=true&limit=200` | Alerts, highest level first. Fields: `id`, `nodeId`, `level`, `peakLevelRank`, `depthM`, `message`, `openedAt`, `updatedAt`, `resolvedAt`, `acknowledgedBy` |
| `POST /alerts/{alert_id}/ack` | Acknowledge an alert |

An alert opens when a node reaches `alert_min_level` (default Moderate) and closes when the node drops below it again.

### Activity log

`GET /logs?status=&limit=200` returns entries with `timestamp`, `officialId`, `refId`, `action`, `description`, `status` (`PENDING`, `COMPLETED`, `REJECTED`) and `measures` (the current measures of the report the entry refers to, for report actions). Action codes include `SET_RAINFALL`, `RESET_SIMULATION`, `BLOCK_NODE`, `UNBLOCK_NODE`, `APPROVE_REPORT`, `REJECT_REPORT`, `RESOLVE_REPORT`, `UPDATE_REPORT_MEASURES` and `UPDATE_CONFIG`. The frontend shows them as words ("Approve Report").

### Settings

| Endpoint | Purpose |
|---|---|
| `GET /config` | Current values |
| `PUT /config` | Body `{ "changes": { "alert_min_level": "HIGH" } }`. Invalid values return `422` |

| Setting | Default | Meaning |
|---|---|---|
| `thresholds.low_m` | 0.03 | any visible water |
| `thresholds.moderate_m` | 0.15 | Moderate |
| `thresholds.high_m` | 0.30 | High |
| `thresholds.critical_m` | 0.60 | Critical |
| `thresholds.route_block_m` | 0.15 | depth above which streets are penalised in routing |
| `alert_min_level` | MODERATE | lowest level that raises an alert |
| `log_retention_days` | 90 | 0 keeps logs forever |
| `prediction_retention_days` | 7 | cannot be 0 |
| `alert_retention_days` | 90 | |

### Pipe capacity (experimental)

`GET /blockage`, `POST /blockage` (body `{ "blockages": [{ "edge_idx": 12, "capacity_fraction": 0.4 }], "replace": false }`, fraction from 0.1 to 1.0) and `DELETE /blockage` set how much of each pipe is open. The model only uses this when `BLOCKAGE_EFFECTIVE=true`, and its reaction to blockage is weak (see `docs/MODEL_REPORT.md`).
