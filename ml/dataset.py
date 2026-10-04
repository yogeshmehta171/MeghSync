"""
dataset.py  (v2)

What changed compared with the old file:
  * Windows are cut lazily (the old file kept every window in RAM, ~GBs).
  * Each sample now has K future steps (for multi-step rollout training).
  * Rain is aligned the way the live server uses it: the rain channel at each
    window position is the rain of the interval that LEADS INTO the next state.
  * New rain channel: rainfall accumulated over the last 6 h (antecedent wetness).
  * Static node features (from out/nodes.csv) and optional static edge features
    (dataset/edge_static.npy) are loaded and normalised.
  * Optional "dry windows": no rain, no flooding, resting depth -> teaches the model
    that a dry city stays dry.
  * Node depth is also a target now (the old code only predicted flood).
"""
import os
import warnings

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset

# ---- single source of truth for scaling (import these elsewhere, never retype) ----
FLOOD_MAX_M = 2.5          # max surface flood depth used for scaling
DEPTH_MAX_M = 10.0         # max node depth used for scaling
RAIN_MAX_MMHR = 150.0      # max rain intensity used for scaling
ANTECEDENT_MAX_MM = 200.0  # max rain accumulated over the last 6 h used for scaling
ANTECEDENT_STEPS = 72      # 72 x 5 min = 6 h
STEP_MINUTES = 5
WET_M = 0.03               # a node is "wet" (flooding) at or above this surface depth
SEQ_LEN = 12


def rolling_rain_mm(rain_mmhr, window=ANTECEDENT_STEPS):
    """Rain accumulated (mm) over the last `window` steps, including the current one."""
    mm = np.asarray(rain_mmhr, dtype=np.float64) * STEP_MINUTES / 60.0
    c = np.cumsum(mm)
    out = c.copy()
    if len(c) > window:
        out[window:] = c[window:] - c[:-window]
    return out.astype(np.float32)


def fit_length(arr, n):
    arr = np.asarray(arr, dtype=np.float32)
    if len(arr) >= n:
        return arr[:n]
    return np.pad(arr, (0, n - len(arr)))


def load_node_static(nodes_csv="out/nodes.csv"):
    """All numeric columns of nodes.csv (except ids and coordinates), z-scored."""
    if not os.path.exists(nodes_csv):
        print(f"[dataset] {nodes_csv} not found -> no static node features")
        return None, []
    df = pd.read_csv(nodes_csv)
    skip = {"id", "idx", "index", "node", "node_id", "name", "lat", "lon", "latitude", "longitude", "x", "y"}
    cols = [c for c in df.columns if c.lower() not in skip and pd.api.types.is_numeric_dtype(df[c])]
    if not cols:
        return None, []
    arr = np.nan_to_num(df[cols].to_numpy(np.float32))
    mean, std = arr.mean(0), arr.std(0)
    std[std < 1e-6] = 1.0
    return ((arr - mean) / std).astype(np.float32), cols


def load_edge_static(data_dir="dataset"):
    path = f"{data_dir}/edge_static.npy"
    if not os.path.exists(path):
        return None
    arr = np.nan_to_num(np.load(path).astype(np.float32))
    if arr.ndim == 1:
        arr = arr[:, None]
    mean, std = arr.mean(0), arr.std(0)
    std[std < 1e-6] = 1.0
    return ((arr - mean) / std).astype(np.float32)


def compute_dry_baseline(data_dir="dataset", rain_file="synthetic_storms_mm_hr.npy", storm_indices=range(210)):
    """
    Resting node depth (m) per node = median depth over all samples that are dry AND
    before any rain has fallen. If SWMM starts from empty pipes this is simply zeros.
    """
    rain_all = np.load(rain_file)
    acc = []
    for i in storm_indices:
        try:
            flood = np.load(f"{data_dir}/flood_storm_{i:03d}.npy")
            depth = np.load(f"{data_dir}/depth_storm_{i:03d}.npy")
        except FileNotFoundError:
            continue
        cum = rolling_rain_mm(fit_length(rain_all[i], flood.shape[0]))
        mask = (cum <= 1e-6)[:, None] & (flood < WET_M)
        acc.append(np.where(mask, depth, np.nan))
    if not acc:
        raise SystemExit("compute_dry_baseline: no storm files found.")
    allv = np.concatenate(acc, axis=0)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        base = np.nanmedian(allv, axis=0)
    return np.nan_to_num(base).astype(np.float32)


class UrbanFloodDataset(Dataset):
    def __init__(self, data_dir="dataset", rain_file="synthetic_storms_mm_hr.npy", storm_indices=None,
                 seq_len=SEQ_LEN, horizon=4, n_dry_windows=0, dry_baseline=None, nodes_csv="out/nodes.csv"):
        self.L, self.K = seq_len, horizon
        self.edge_index = torch.load(f"{data_dir}/edge_index.pt", map_location="cpu")
        if storm_indices is None:
            storm_indices = range(300)

        try:
            rain_all = np.load(rain_file)
        except FileNotFoundError:
            raise FileNotFoundError(f"Could not find {rain_file}. Put it in the folder you run Python from.")

        ns, self.node_static_cols = load_node_static(nodes_csv)
        self.node_static = torch.tensor(ns) if ns is not None else None
        es = load_edge_static(data_dir)
        self.edge_static = torch.tensor(es) if es is not None else None

        self.flood, self.depth, self.rain, self.cum, self.cap = [], [], [], [], []
        self.index = []
        skipped = []
        for i in storm_indices:
            try:
                f = np.load(f"{data_dir}/flood_storm_{i:03d}.npy").astype(np.float32)
                d = np.load(f"{data_dir}/depth_storm_{i:03d}.npy").astype(np.float32)
                b = np.load(f"{data_dir}/blockage_storm_{i:03d}.npy").astype(np.float32)
            except FileNotFoundError:
                skipped.append(i)
                continue
            if b.shape[0] != self.edge_index.shape[1]:
                raise ValueError(f"storm {i}: blockage has {b.shape[0]} entries but edge_index has "
                                 f"{self.edge_index.shape[1]} edges")
            T = f.shape[0]
            r = fit_length(rain_all[i], T)
            s = len(self.flood)
            self.flood.append(f); self.depth.append(d); self.rain.append(r)
            self.cum.append(rolling_rain_mm(r)); self.cap.append(b)
            for a in range(T - seq_len - horizon):
                self.index.append((s, a))
        if skipped:
            print(f"[dataset] WARNING: {len(skipped)} storms missing, skipped: {skipped}")
        if not self.flood:
            raise SystemExit("No storm files were loaded. Check the dataset/ folder.")

        self.n_nodes = self.flood[0].shape[1]
        self.n_real = len(self.index)
        allf = np.concatenate([f.ravel() for f in self.flood])
        self.wet_fraction = float((allf >= WET_M).mean())

        self.dry_baseline = None if dry_baseline is None else np.asarray(dry_baseline, dtype=np.float32)
        self.n_dry = int(n_dry_windows) if self.dry_baseline is not None else 0
        print(f"[dataset] storms: {len(self.flood)} | real windows: {self.n_real} | dry windows: {self.n_dry} | "
              f"nodes: {self.n_nodes} | wet fraction: {self.wet_fraction:.4f}")
        if self.node_static is not None:
            print(f"[dataset] static node features used: {self.node_static_cols}")

    def __len__(self):
        return self.n_real + self.n_dry

    def __getitem__(self, idx):
        L, K = self.L, self.K
        if idx < self.n_real:
            s, a = self.index[idx]
            f, d = self.flood[s], self.depth[s]
            return dict(
                flood_hist=torch.from_numpy(f[a:a + L].T.copy()),            # [N, L]
                depth_hist=torch.from_numpy(d[a:a + L].T.copy()),
                flood_fut=torch.from_numpy(f[a + L:a + L + K].T.copy()),     # [N, K]
                depth_fut=torch.from_numpy(d[a + L:a + L + K].T.copy()),
                rain=torch.from_numpy(self.rain[s][a + 1:a + L + K + 1].copy()),   # [L+K]
                cum=torch.from_numpy(self.cum[s][a + 1:a + L + K + 1].copy()),
                cap=torch.from_numpy(self.cap[s].copy()),                    # [E]
            )
        # dry window: nothing falls, nothing floods, water stays at its resting depth
        j = idx - self.n_real
        base = torch.from_numpy(self.dry_baseline)
        n = base.shape[0]
        return dict(
            flood_hist=torch.zeros(n, L),
            depth_hist=base[:, None].repeat(1, L),
            flood_fut=torch.zeros(n, K),
            depth_fut=base[:, None].repeat(1, K),
            rain=torch.zeros(L + K),
            cum=torch.zeros(L + K),
            cap=torch.from_numpy(self.cap[j % len(self.cap)].copy()),
        )


if __name__ == "__main__":
    base = compute_dry_baseline(storm_indices=range(0, 20))
    print("dry baseline depth (m): min %.3f median %.3f max %.3f" % (base.min(), np.median(base), base.max()))
    ds = UrbanFloodDataset(storm_indices=range(0, 5), n_dry_windows=10, dry_baseline=base)
    s = ds[0]
    for k, v in s.items():
        print(f"{k:11s} {tuple(v.shape)}")