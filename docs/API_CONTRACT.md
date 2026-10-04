# API contract (backend v2)

Base URL `http://localhost:8000`. JSON. Admin endpoints need `Authorization: Bearer <token>` from `/api/auth/login`.
Every data response carries `meta` (freshness): `computedAt, ageSeconds, stale, modelSource ("gnn"|"mock"), modelVersion,
isMockData, rainMmHr, horizonHours, confidence, blockageEffective`. The UI should grey out and warn when `meta.stale` is true.

## Public (citizens)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | liveness + freshness |
| GET | `/api/nodes?hours=0\|0.5\|1\|2\|3` | `{data: Node[], meta}`. Official-only fields are blank/absent |
| GET | `/api/pipes` | drainage GeoJSON |
| POST | `/api/route` | body `{start:{lat,lon}, destination:{lat,lon}}` -> `{safe, normal, extraM, extraEtaMin, normalRouteFlooded, unavoidableFlood, message, meta}`; `safe/normal = {path:[[lat,lng]..], lengthM, etaMin, floodedLengthM, penalizedSegments}` |
| POST | `/api/reports` | body `{name, phone, location, description, lat?, lon?}` -> `201 {id, status:"PENDING", timestamp}`. 5 per hour per IP |
| GET | `/api/reports/{id}/status` | `{id, status, timestamp}` |

## Auth
| POST | `/api/auth/login` | `{municipality_id, password}` -> `{token, expiresInSeconds, user}`; 10 tries/min/IP |
| GET | `/api/auth/me` | current user |

## Municipality (all require login)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/admin/nodes?hours=` | full Node list: `suggestedAction`, `blockSource`, `predicted{0.5,1.0,2.0,3.0}`, `state` (NORMAL/INCREASED_LEVEL/SURCHARGE/SURFACE_FLOODING/SEVERE), `alertLevel` |
| GET | `/api/admin/nodes/{id}` | node + `recent[]` (last 12 ticks, cm) + pipe depth |
| GET | `/api/admin/overview` | level counts, max flood, blocked, open alerts, per-horizon summary |
| POST | `/api/admin/rain` | `{rain_mm_hr}` 0..500 |
| POST | `/api/admin/reset` | `{clear_blocks?: false}`. Blocks are KEPT by default |
| GET/POST | `/api/admin/blocks` | list / manual block `{node_id}` or `{lat,lon}` (nearest node within 250 m) |
| DELETE | `/api/admin/blocks/{node_id}` | release |
| GET | `/api/admin/reports?status=` | Report[] (+ `matchedNodeId`, `lat`, `lon`, reviewer) |
| POST | `/api/admin/reports/{id}/approve` | optional `{node_id, note}`; creates a persistent block, logs, re-prices streets immediately |
| POST | `/api/admin/reports/{id}/reject` · `/resolve` | `resolve` releases the block |
| GET | `/api/admin/alerts?active=true` · POST `/{id}/ack` | automatic alerts |
| GET | `/api/admin/logs?status=&limit=` | `{timestamp, officialId, refId, action, description, status}` |
| GET/PUT | `/api/admin/config` | `{changes:{thresholds, alert_min_level, log_retention_days, prediction_retention_days, alert_retention_days}}` |
| GET/POST/DELETE | `/api/admin/blockage` | pipe capacity (EXPERIMENTAL: the current model barely reacts to it) |

## Removed from the old backend
`/api/predict`, `/api/forecast`, `/api/override` (replaced by `/api/nodes`, `/api/admin/nodes?hours=`, `/api/admin/blocks`).
`/api/rain`, `/api/reset`, `/api/blockage` moved under `/api/admin/` and now require login.

## Defaults you may want to change in the dashboard (Settings)
Risk thresholds (surface flood, metres): LOW 0.03, MODERATE 0.15 (= routes avoid it), HIGH 0.30, CRITICAL 0.60.
Alerts are raised from MODERATE up. Log retention 90 days, prediction history 7 days.
