# Frontend

React 18 + TypeScript, built with Vite. Styling uses Tailwind CSS with shadcn-style components. Maps use Leaflet through react-leaflet. Charts use Recharts, routing uses React Router.

## Run, check and build

```powershell
cd frontend
npm install
npm run dev                  # http://localhost:5173
npx tsc --noEmit             # strict type check
npm run build                # production build
```

The backend address comes from `VITE_API_URL` (default `http://localhost:8000`). Set it in `frontend/.env.local` (not committed).

## Pages

| Route | Page | Who | What it shows |
|---|---|---|---|
| `/` | Home | public | Live map of the drainage grid, feature cards, footer with Privacy Policy and Terms of Service pop-ups |
| `/routing` | Safe Route | public | Pick a start and destination; shows the normal route (orange, dashed) and the flood-safe route (green) with distance, time and extra detour |
| `/report` | Flood report | public | Name, phone, location, description, optional map pin or GPS |
| `/login` | Login | officials | Municipality ID and password |
| `/admin/dashboard` | Overview | officials | Command center map and panels (below) |
| `/admin/nodes` | Nodes | officials | Table of all nodes with risk filter |
| `/admin/reports` | Citizen Report | officials | Report inbox with pending count, approve dialog, Measures column, CSV export |
| `/admin/logs` | Logs | officials | Activity log in two sections, Citizen Report and System & Simulation, each with CSV export |

### Command center panels (side bar)

Emergency routing (Node tab and Location tab, pick points on the map, normal and safe route with a comparison), rainfall control (0 to 150 mm/hr and reset), nowcasting (now, +30 min, +1 h, +2 h, +3 h), predicted impact (nodes at risk), active alerts, node inspector, graphical analysis (deepest flooding now and in the forecast), citizen reports, and blocked nodes (list, show on map, unblock).

## How data flows

* `src/api/api.ts` is a thin client. The login token is kept in `sessionStorage` (cleared when the tab closes).
* `src/context/PravahaContext.tsx` holds the shared state: nodes, forecasts, reports, logs, alerts and the freshness `meta`. It polls the backend every 5 seconds and exposes actions such as `approveReport`, `rejectReport`, `saveMeasures`, `blockNode` and `unblockNode`.
* `src/context/PravahaContext.mock.tsx` is an older stand-in with fake data. It may need updates before use.
* `src/types/index.ts` holds the shared types. The API shapes are in `API_CONTRACT.md`.

## Folder map

```
src/pages/        one file per page
src/components/   shared pieces (place picker, approve dialog, blocked-node badge, legal pop-up, brand logo, ui/)
src/context/      shared state
src/api/          backend client
src/lib/          csv.ts (CSV download), legal.ts (policy text), utils.ts
public/           images and the logo
```

## Notes

* The CSV export builds the file in the browser. Cells that start with `=`, `+`, `-` or `@` get a leading `'` so spreadsheets never run citizen text as a formula.
* Action codes from the server (for example `APPROVE_REPORT`) are shown as words ("Approve Report").
