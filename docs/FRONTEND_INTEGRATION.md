# Connecting Chaitanya's frontend (nothing in `frontend/` has been edited)

Today the whole UI reads mock data from `src/context/PravahaContext.tsx` and makes no network calls.
`docs/frontend-integration/` holds two new files that keep the **same `usePravaha()` interface**, so the pages do not change:

1. `api.ts` -> copy to `frontend/src/api/api.ts`
2. `PravahaContext.live.tsx` -> copy over `frontend/src/context/PravahaContext.tsx` (keep the old one as `.mock.tsx` if you want a demo mode)
3. Create `frontend/.env.local` with `VITE_API_URL=http://localhost:8000`

That alone makes Home / Routing map markers / Nodes / Dashboard / Reports / Logs show live data and makes rainfall work.
Five small page edits are still needed, because those pages fake the behaviour locally:

| File | Change |
|---|---|
| `pages/Login.tsx` | `handleLogin`: `await login(id, pwd)` from `usePravaha()`, then `navigate('/admin/dashboard')`; show the error on failure |
| `App.tsx` | wrap the `/admin/*` routes in a guard: `if (!isAuthenticated) return <Navigate to="/login" />`; Logout link calls `logout()` |
| `pages/Reports.tsx` | `approveReport(report.id, nodes[0].id)` passes the FIRST node, which would block the wrong place. Use `report.matchedNodeId`; if null, show a node picker |
| `pages/CitizenReport.tsx` | use the id returned by `addReport` instead of `'R' + Math.random()`; send `lat/lon` from the GPS/mini-map if available |
| `pages/CitizenRouting.tsx` | call `findRoute(start, dest)`; the inputs are free text and there is **no geocoder**, so use map clicks or browser GPS for start/destination |

Also: the Dashboard popup "BLOCK (NODE)" button has no handler; connect it to `blockNode(node.id)`.
The drainage `Polyline` on the dashboard joins the node dots in list order; replace it with `GET /api/pipes`.
Not yet testable here: these files were written without being able to run `npm run build`; run it and fix any type errors.
