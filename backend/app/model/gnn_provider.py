"""
Wraps Maanas's v2 FloodASTGCN (ml/model.py). The inference maths below is copied from the v2 app.py he supplied,
so behaviour is identical; only the packaging changed. torch is imported lazily so the mock provider and the
unit tests run without it.
"""
from __future__ import annotations

import sys
from collections import deque
from pathlib import Path
from typing import Optional

import numpy as np

from .base import SEQ_LEN, STEP_MINUTES, NodeState

ANTECEDENT_STEPS = 72                       # 6 h of 5-minute steps, matches dataset.py
RAIN_HISTORY_LEN = SEQ_LEN + ANTECEDENT_STEPS   # 84


class GnnProvider:
    name = "gnn"

    def __init__(self, ml_dir: Path, model_path: Path, n_nodes: int):
        import torch  # noqa: lazy
        self._torch = torch
        sys.path.insert(0, str(ml_dir))            # makes `model` and `dataset` from ml/ importable
        from model import load_model, build_x, rollout, decode  # noqa
        self._build_x, self._rollout, self._decode = build_x, rollout, decode

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.model, dry_baseline = load_model(str(model_path), self.device)
        cfg = self.model.config
        if cfg["n_nodes"] != n_nodes:
            raise RuntimeError(
                f"Model was trained on {cfg['n_nodes']} nodes but the database has {n_nodes}. "
                "Wrong checkpoint, or manholes table not loaded from the same network.")
        self.n_nodes, self.n_edges = cfg["n_nodes"], cfg["n_edges"]
        self.version = f"astgcn-v2:{Path(model_path).name}"
        self._dry_step = np.zeros((n_nodes, 2), dtype=np.float32)
        if dry_baseline is not None:
            self._dry_step[:, 1] = np.asarray(dry_baseline, dtype=np.float32)
        self.reset()

    # ------------------------------------------------------------------ state
    def reset(self) -> None:
        self._history = deque([self._dry_step.copy() for _ in range(SEQ_LEN)], maxlen=SEQ_LEN)
        self._rain_hist = deque([0.0] * RAIN_HISTORY_LEN, maxlen=RAIN_HISTORY_LEN)

    # ---------------------------------------------------------------- helpers
    def _cap_tensor(self, capacity: Optional[np.ndarray]):
        torch = self._torch
        if capacity is None:
            cap = np.ones(self.n_edges, dtype=np.float32)
        else:
            cap = np.asarray(capacity, dtype=np.float32)
            if cap.shape[0] != self.n_edges:
                raise ValueError(f"capacity has {cap.shape[0]} entries, model expects {self.n_edges}")
        return torch.tensor(cap, device=self.device).unsqueeze(0)

    def _hist_tensors(self):
        torch = self._torch
        hf = np.stack([h[:, 0] for h in self._history], axis=1)
        hd = np.stack([h[:, 1] for h in self._history], axis=1)
        return (torch.tensor(hf, dtype=torch.float32, device=self.device).unsqueeze(0),
                torch.tensor(hd, dtype=torch.float32, device=self.device).unsqueeze(0))

    # ------------------------------------------------------------------- live
    def step(self, rain_mm_hr: float, capacity: Optional[np.ndarray]) -> NodeState:
        torch = self._torch
        self._rain_hist.append(float(rain_mm_hr))
        rh = list(self._rain_hist)
        rain_win = np.array(rh[-SEQ_LEN:], dtype=np.float32)
        cum_win = np.array([sum(rh[i + 1: i + 1 + ANTECEDENT_STEPS]) * (STEP_MINUTES / 60.0)
                            for i in range(SEQ_LEN)], dtype=np.float32)
        fh, dh = self._hist_tensors()
        r_t = torch.tensor(rain_win, device=self.device).unsqueeze(0)
        c_t = torch.tensor(cum_win, device=self.device).unsqueeze(0)
        x = self._build_x(fh, dh, r_t, c_t)
        with torch.no_grad():
            out = self.model(x, self._cap_tensor(capacity))
            flood, depth, _ = self._decode(out, hard=True)
        new = np.zeros((self.n_nodes, 2), dtype=np.float32)
        new[:, 0] = flood[0].cpu().numpy()
        new[:, 1] = depth[0].cpu().numpy()
        self._history.append(new)
        return NodeState(flood_m=new[:, 0].copy(), depth_m=new[:, 1].copy())

    # --------------------------------------------------------------- forecast
    def forecast(self, rain_mm_hr: float, capacity: Optional[np.ndarray], steps: list[int]) -> dict[int, np.ndarray]:
        torch = self._torch
        max_steps = max(steps)
        rh = list(self._rain_hist)
        future = rh + [float(rain_mm_hr)] * max_steps
        req_len = SEQ_LEN + max_steps
        rain_win = np.array(future[-req_len:], dtype=np.float32)
        start_idx = len(future) - req_len
        cum_win = np.zeros(req_len, dtype=np.float32)
        for j in range(req_len):
            end = start_idx + j + 1
            cum_win[j] = sum(future[max(0, end - ANTECEDENT_STEPS):end]) * (STEP_MINUTES / 60.0)
        fh, dh = self._hist_tensors()
        r_t = torch.tensor(rain_win, device=self.device).unsqueeze(0)
        c_t = torch.tensor(cum_win, device=self.device).unsqueeze(0)
        with torch.no_grad():
            results = self._rollout(self.model, fh, dh, r_t, c_t, self._cap_tensor(capacity),
                                    steps=max_steps, hard=True)
        return {k: results[k - 1]["flood"][0].cpu().numpy().astype(np.float32) for k in steps}
