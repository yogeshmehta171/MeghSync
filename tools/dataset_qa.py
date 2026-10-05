"""
dataset_qa.py: checks a storm dataset before it is used for training.

Run from the training folder (the one that holds dataset/, synthetic_storms_mm_hr.npy and out/nodes.csv):

    python dataset_qa.py
    python dataset_qa.py --first 300 --last 599          # only check storms 300 to 599
    python dataset_qa.py --pairs pairs.csv               # also check paired runs (see below)

What it checks, per storm:
  * the three files exist (flood, depth, blockage)
  * shapes: flood and depth are [time, nodes] and match each other, blockage has one value per pipe
  * no NaN or infinite values, flood never negative, flood not above the model's scale (2.5 m) by much
  * blockage values are between 0.1 and 1.0
  * the rain row exists and is long enough (rain is padded with zeros if shorter than the run)
It also prints a summary (number of storms, deepest flood, blocked storms) so the new data can be compared with the old.

pairs.csv (optional) has two columns, `reference,variant`: storm ids that must have IDENTICAL rain
(for example the same storm run without and with blockage).

Needs numpy only. If PyTorch is installed it also checks dataset/edge_index.pt.
"""
import argparse
import csv
import os
import sys

import numpy as np

N_NODES_DEFAULT = 662
N_EDGES_DEFAULT = 661
FLOOD_SCALE_M = 2.5          # ml/dataset.py FLOOD_MAX_M


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default="dataset")
    ap.add_argument("--rain", default="synthetic_storms_mm_hr.npy")
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--last", type=int, default=299)
    ap.add_argument("--nodes", type=int, default=N_NODES_DEFAULT)
    ap.add_argument("--edges", type=int, default=N_EDGES_DEFAULT)
    ap.add_argument("--pairs")
    a = ap.parse_args()

    problems, warnings = [], []

    def bad(msg):
        problems.append(msg)

    def warn(msg):
        warnings.append(msg)

    # ---- rain file
    rain = None
    if os.path.exists(a.rain):
        try:
            rain = np.load(a.rain)          # the training code loads it the same way (no allow_pickle)
            if rain.ndim != 2:
                bad(f"{a.rain}: expected a 2-D array [storms, steps], got shape {rain.shape}")
                rain = None
            else:
                print(f"{a.rain}: shape {rain.shape}")
        except Exception as e:  # noqa
            bad(f"{a.rain}: cannot be loaded without allow_pickle ({e}). Pad every row to one length.")
    else:
        bad(f"{a.rain} not found")

    # ---- edge index (optional, needs torch)
    ei_path = os.path.join(a.data_dir, "edge_index.pt")
    if os.path.exists(ei_path):
        try:
            import torch
            ei = torch.load(ei_path, map_location="cpu")
            if tuple(ei.shape) != (2, a.edges):
                bad(f"edge_index.pt has shape {tuple(ei.shape)}, expected (2, {a.edges})")
            else:
                print(f"edge_index.pt: shape {tuple(ei.shape)} ok")
        except ImportError:
            warn("PyTorch not installed: edge_index.pt not checked")
    else:
        bad(f"{ei_path} not found")

    # ---- storms
    stats = dict(n=0, max_flood=[], blocked=0, lengths=set(), missing=[])
    for i in range(a.first, a.last + 1):
        paths = {k: os.path.join(a.data_dir, f"{k}_storm_{i:03d}.npy") for k in ("flood", "depth", "blockage")}
        miss = [k for k, p in paths.items() if not os.path.exists(p)]
        if miss:
            stats["missing"].append(i)
            if len(miss) < 3:
                bad(f"storm {i}: missing {', '.join(miss)} (all three files must exist)")
            continue
        f, d, b = (np.load(paths[k]) for k in ("flood", "depth", "blockage"))
        tag = f"storm {i}"
        if f.ndim != 2 or f.shape[1] != a.nodes:
            bad(f"{tag}: flood shape {f.shape}, expected [time, {a.nodes}]")
            continue
        if d.shape != f.shape:
            bad(f"{tag}: depth shape {d.shape} differs from flood shape {f.shape}")
        if b.shape != (a.edges,):
            bad(f"{tag}: blockage shape {b.shape}, expected ({a.edges},)")
        for name, arr in (("flood", f), ("depth", d), ("blockage", b)):
            if not np.isfinite(arr).all():
                bad(f"{tag}: {name} has NaN or infinite values")
        if (f < -1e-6).any():
            bad(f"{tag}: flood has negative values (min {f.min():.3f})")
        if f.max() > 1.25 * FLOOD_SCALE_M:
            warn(f"{tag}: deepest flood {f.max():.2f} m is far above the model's 2.5 m scale")
        if b.size == a.edges and ((b < 0.1 - 1e-6).any() or (b > 1.0 + 1e-6).any()):
            bad(f"{tag}: blockage values must be between 0.1 and 1.0 (found {b.min():.3f} to {b.max():.3f})")
        if rain is not None:
            if i >= rain.shape[0]:
                bad(f"{tag}: no rain row (the rain file has {rain.shape[0]} rows)")
            else:
                r = rain[i]
                if not np.isfinite(r).all() or (r < 0).any():
                    bad(f"{tag}: rain row has NaN or negative values")
                if r.shape[0] < f.shape[0]:
                    stats["short_rain"] = stats.get("short_rain", 0) + 1       # normal: the original data has 36 rain steps and 59 simulated steps
        stats["n"] += 1
        stats["max_flood"].append(float(f.max()))
        stats["lengths"].add(int(f.shape[0]))
        stats["blocked"] += int((b < 1.0).any())

    # ---- pairs
    if a.pairs and rain is not None:
        with open(a.pairs, newline="") as fh:
            for row in csv.DictReader(fh):
                r1, r2 = int(row["reference"]), int(row["variant"])
                if r1 >= rain.shape[0] or r2 >= rain.shape[0] or not np.allclose(rain[r1], rain[r2]):
                    bad(f"pair {r1},{r2}: the rain is not identical")

    # ---- report
    print(f"\nstorms checked: {stats['n']} (ids {a.first} to {a.last}); run lengths seen: {sorted(stats['lengths'])}")
    if stats["max_flood"]:
        mf = np.array(stats["max_flood"])
        print(f"deepest flood per storm (m): min {mf.min():.2f} | median {np.median(mf):.2f} | max {mf.max():.2f}")
        print(f"storms with blockage: {stats['blocked']} of {stats['n']}")
    if stats.get("short_rain"):
        print(f"info: in {stats['short_rain']} storms the rain row is shorter than the simulation (normal: the missing steps count as no rain)")
    if stats["missing"]:
        print(f"storms with no files at all: {len(stats['missing'])} (first few: {stats['missing'][:10]})")
    for w in warnings[:20]:
        print("WARNING:", w)
    if len(warnings) > 20:
        print(f"... and {len(warnings) - 20} more warnings")
    for p in problems[:40]:
        print("PROBLEM:", p)
    if len(problems) > 40:
        print(f"... and {len(problems) - 40} more problems")
    print("\nRESULT:", "no problems found" if not problems else f"{len(problems)} problem(s) found: fix them before training")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
