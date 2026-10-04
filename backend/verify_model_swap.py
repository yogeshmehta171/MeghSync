"""
verify_model_swap.py: checks that a model file works with the real backend code before you rely on it.

Run from the backend folder (nothing else needs to be running; the database is not used):

    python verify_model_swap.py ..\\ml\\checkpoints_v3\\best_model_v3.pt
    python verify_model_swap.py ..\\ml\\checkpoints_v3\\best_model_v3.pt --compare ..\\ml\\checkpoints_v2\\best_model.pt

It loads the model through the SAME class the server uses (app/model/gnn_provider.py), then checks:
loads and matches the 662-node network, zero rain stays dry, no absurd values at any rain level,
forecasts have the right shape, blocked-pipe input is accepted, and speed.
Add --mock to test this script itself without PyTorch.
"""
import argparse
import statistics
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
N_NODES = 662
BLOCK_M = 0.15


def make(path, mock):
    if mock:
        from app.model.mock_provider import MockProvider
        return MockProvider(N_NODES)
    from app.model.gnn_provider import GnnProvider
    return GnnProvider(HERE.parent / "ml", Path(path), N_NODES)


def run(p, label):
    results, info = [], []

    def check(name, ok, detail=""):
        results.append(ok)
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f": {detail}" if detail else ""))

    print(f"\n=== {label}  (version {p.version}) ===")
    check("model matches the database network", p.n_nodes == N_NODES, f"{p.n_nodes} nodes, {p.n_edges} pipes")

    # zero rain must stay dry
    p.reset()
    worst_flood = worst_depth = 0.0
    for _ in range(36):
        s = p.step(0.0, None)
        worst_flood, worst_depth = max(worst_flood, float(s.flood_m.max())), max(worst_depth, float(s.depth_m.max()))
    check("zero rain for 3 h gives no flooding", worst_flood == 0.0, f"max flood {worst_flood:.3f} m")
    print(f"  [INFO] zero rain: largest node-depth drift {worst_depth:.3f} m (about 0.02 m for the fine-tuned model, 0.36 m for the old one)")

    # rain sweep: finite, bounded, more rain -> not fewer flooded nodes
    counts, sane = [], True
    for rain in (10, 30, 60, 90, 120, 150):
        p.reset()
        for _ in range(12):
            s = p.step(float(rain), None)
        f = s.flood_m
        sane &= bool(np.isfinite(f).all() and (f >= 0).all() and f.max() <= 3.76)
        counts.append(int((f >= BLOCK_M).sum()))
    check("rain sweep 10 to 150 mm/hr: values finite, between 0 and 3.75 m", sane)
    check("more rain never gives clearly fewer flooded nodes", all(b >= a - 5 for a, b in zip(counts, counts[1:])),
          "nodes above 15 cm after 1 h at 10/30/60/90/120/150 mm/hr = " + str(counts))

    # forecast shape and values
    p.reset()
    for _ in range(12):
        p.step(60.0, None)
    fc = p.forecast(60.0, None, [6, 12, 24, 36])
    ok = set(fc) == {6, 12, 24, 36} and all(v.shape == (N_NODES,) and np.isfinite(v).all() and (v >= 0).all() for v in fc.values())
    check("forecast returns +30 min, +1 h, +2 h, +3 h for all nodes", ok,
          "nodes above 15 cm = " + ", ".join(f"+{k * 5} min: {int((v >= BLOCK_M).sum())}" for k, v in sorted(fc.items())))

    # blocked-pipe input accepted (only for models that use it)
    if p.n_edges:
        cap = np.ones(p.n_edges, dtype=np.float32)
        cap[:50] = 0.3
        try:
            p.reset()
            s = p.step(60.0, cap)
            check("pipe capacity input accepted", s.flood_m.shape == (N_NODES,))
        except Exception as e:  # noqa
            check("pipe capacity input accepted", False, repr(e))

    # speed (informational)
    p.reset()
    times = []
    for _ in range(20):
        t = time.perf_counter()
        p.step(60.0, None)
        times.append((time.perf_counter() - t) * 1000)
    print(f"  [INFO] one step takes {statistics.median(times):.0f} ms (median of 20). The server ticks every 5000 ms.")

    # staged flooding (informational)
    p.reset()
    stages = []
    for i in range(1, 25):
        s = p.step(90.0, None)
        if i in (3, 6, 12, 24):
            stages.append(int((s.flood_m >= BLOCK_M).sum()))
    print(f"  [INFO] 90 mm/hr: nodes above 15 cm after 15 / 30 / 60 / 120 min = {stages}")
    return all(results), counts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", default=str(HERE.parent / "ml" / "checkpoints_v2" / "best_model.pt"))
    ap.add_argument("--compare", help="a second model file to run the same checks on")
    ap.add_argument("--mock", action="store_true", help="test this script without PyTorch")
    a = ap.parse_args()
    ok, _ = run(make(a.model, a.mock), a.model)
    if a.compare:
        run(make(a.compare, a.mock), a.compare)
    print("\nRESULT:", "all checks passed" if ok else "SOME CHECKS FAILED, do not use this model yet")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
