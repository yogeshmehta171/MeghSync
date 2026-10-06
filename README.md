# MeghSync: T. Nagar flood Nowcasting and Safe Routing

MeghSync predicts street-level flooding for T. Nagar, Chennai, now and for the next 3 hours, and gives people routes that avoid flooded streets. Municipal officials get a command center. Citizens get a public site with a safe-route planner and a flood report form.

The system learns from 300 synthetic storms simulated with EPA SWMM. A graph neural network imitates the simulator on a 662-node drainage graph, so a prediction takes about 0.1 second on an ordinary CPU. (The repository folder and some code still use the earlier project name Pravaha-X.)

## What it does

* **Prediction:** flood depth at 662 nodes for now, +30 min, +1 h, +2 h and +3 h, for a rainfall intensity set by an official (0 to 150 mm/hr).
* **Risk and alerts:** five risk levels (Safe, Low 3 cm, Moderate 15 cm, High 30 cm, Critical 60 cm; configurable). Alerts start at Moderate.
* **Routing:** A* inside the database. Streets within 75 m of a node deeper than 15 cm cost 10,000 times more, so routes avoid them. The normal and the flood-safe route are shown together with distance, time and the extra detour.
* **Citizen reports:** a citizen sends a report with an optional map pin. An official approves or rejects it, picks the node to block and records the measures taken.
* **Command center:** risk map, rainfall control, forecast scrubber, alerts, graphs, emergency routing with map picking, blocked-nodes panel, activity logs with CSV export.

## Repository layout

```
backend/     FastAPI service, database migrations, tests, test scripts
frontend/    React + TypeScript + Tailwind + Leaflet app (Vite)
ml/          model.py, dataset.py, train.py, test results (check_results_v2.txt, check_results_v3.txt), checkpoints_v2/ (first model), checkpoints_v3/ (fine-tuned model, the default)
db/          base schema and one-time loaders
data/        nodes.csv, links.csv (the 662-node drainage graph)
docs/        API contract, frontend integration notes, retraining report
```

The training dataset and other large files are not in this repository. They are in a shared Google Drive folder: (https://drive.google.com/drive/folders/1jN5j5Dcm4hHAqkBVrDW31zA1D7OpLpaN?usp=sharing)

## Run it (Windows PowerShell, from the project root)

**1. Database** (needs Docker Desktop)

```powershell
copy .env.example .env          # set DB_PASSWORD and POSTGIS_IMAGE (see comments inside)
docker compose up -d
```

The first time, load the network with the steps in `db/README.md`.

**2. Backend** (Python 3.10 or newer, with `torch` and `torch_geometric` installed)

```powershell
cd backend
pip install -r requirements.txt
copy ..\.env.example .env       # edit backend\.env: DATABASE_URL, JWT_SECRET (32+ characters), BOOTSTRAP_ADMIN_ID and BOOTSTRAP_ADMIN_PASSWORD
python scripts\load_node_meta.py ..\data\nodes.csv        # one time
python -m uvicorn app.main:app --port 8000                # one process, never add --workers
```

Delete the two `BOOTSTRAP_ADMIN_*` lines after the first start. API documentation is at http://localhost:8000/docs.

**3. Frontend**

```powershell
cd frontend
npm install
npm run dev                     # http://localhost:5173
```

## The model

The default model is the fine-tuned one, `ml/checkpoints_v3/best_model_v3.pt`. To use the first model, set `MODEL_PATH` in `backend\.env` to the full path of `ml/checkpoints_v2/best_model.pt` and restart.

On 50 storms the model never saw, hazard F1 (flooding deeper than 15 cm) is 0.93 to 0.97 from +5 minutes to +3 hours, and the depth error on flooded nodes is 1.1 cm at +5 minutes and 4.3 cm at +3 hours. The full table is in `ml/check_results_v3.txt` (the first model's results are in `ml/check_results_v2.txt`).

Known limits: it was trained only on synthetic 3-hour storms (none lighter than 11.6 mm/hr), its reaction to blocked pipes is weak, and it has not been compared with real flood records. The forecast assumes the current rainfall continues.

## Documentation

| File | What it covers |
|---|---|
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how the parts fit together, the background loop, routing, report workflow, database, settings |
| [docs/API_CONTRACT.md](docs/API_CONTRACT.md) | every endpoint with inputs, outputs and rules |
| [docs/FRONTEND.md](docs/FRONTEND.md) | pages, shared state, folder map |
| [docs/MODEL_REPORT.md](docs/MODEL_REPORT.md) | the data, the model, training and test results for both models |

## Testing

```powershell
cd backend
python -m unittest discover -s tests                                   # 19 unit tests, no database needed
python verify_model_swap.py ..\ml\checkpoints_v3\best_model_v3.pt      # checks a model file with the real backend code
python live_model_test.py --user YOUR_ADMIN_ID                         # needs the backend running; about 4 minutes
```

Tools for the training data (run from the training folder): `tools/storm_stats.py` describes the storms and `tools/dataset_qa.py` checks the files.

## Large files

The shared Drive folder (view-only link) contains what is too big or too private for GitHub:

| In the Drive folder | What it is |
|---|---|
| `training/dataset/` | the simulated storms: `flood_storm_XXX.npy`, `depth_storm_XXX.npy`, `blockage_storm_XXX.npy`, `edge_index.pt` |
| `training/synthetic_storms_mm_hr.npy`, `training/out/nodes.csv` | the rain for every storm and the node properties used by the model |
| `training/checkpoints/` | every training checkpoint (`checkpoint_epoch_XX.pth`, `last_checkpoint.pt`) so training can be resumed |
| `demo/` | the demo video and the presentation |

Never put `.env` files, passwords or keys in the Drive folder.

## Things to know

* **One worker only.** The live state is in memory and one loop writes to the database.
* **Simulation clock.** One tick (default 5 seconds) advances the model by one 5-minute step, so the demo runs 60 times faster than real time. For real use set `INFERENCE_INTERVAL_SECONDS=300`.
* **Blocks persist** until an official releases them. Resetting the simulation keeps them.
* **Never commit** `.env` files. Before a public launch, change `JWT_SECRET`, remove the `BOOTSTRAP_ADMIN_*` lines and review CORS and the map tile provider.

## Team

See [CONTRIBUTORS.md](CONTRIBUTORS.md).

## Credits and licence

Code: MIT licence (see LICENSE). Street network and map tiles: (c) OpenStreetMap contributors, ODbL. Hydraulic simulation: US EPA SWMM. Libraries: FastAPI, PostgreSQL, PostGIS, pgRouting, React, Leaflet, PyTorch and PyTorch Geometric.
