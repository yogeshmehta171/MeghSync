"""
Mock model: believable, deterministic, needs no torch and no checkpoint.
Used for UI work and tests. It is NOT a flood model and the API labels it as source "mock".
"""
from __future__ import annotations

from collections import deque
from typing import Optional

import numpy as np

from .base import SEQ_LEN, NodeState


class MockProvider:
    name = "mock"
    version = "mock-1"
    n_edges = 0

    def __init__(self, n_nodes: int, seed: int = 7):
        self.n_nodes = n_nodes
        rng = np.random.default_rng(seed)
        self._thr = rng.uniform(8.0, 45.0, n_nodes).astype(np.float32)     # mm/hr where a node starts to flood
        self._gain = rng.uniform(0.5, 2.2, n_nodes).astype(np.float32)     # metres of water per 100 mm/hr over threshold
        self._pipe = rng.uniform(0.2, 0.9, n_nodes).astype(np.float32)
        self.reset()

    def reset(self) -> None:
        self._flood = np.zeros(self.n_nodes, dtype=np.float32)
        self._rain = deque([0.0] * SEQ_LEN, maxlen=SEQ_LEN)

    def _advance(self, flood: np.ndarray, rain_eff: float) -> np.ndarray:
        target = np.clip((rain_eff - self._thr) / 100.0, 0.0, None) * self._gain
        flood = flood + (target - flood) * 0.25
        return np.where(flood < 0.02, 0.0, flood).astype(np.float32)

    def step(self, rain_mm_hr: float, capacity: Optional[np.ndarray]) -> NodeState:
        self._rain.append(float(rain_mm_hr))
        rain_eff = float(np.mean(list(self._rain)[-3:]))
        self._flood = self._advance(self._flood, rain_eff)
        depth = np.clip(self._pipe + self._flood / 2.5, 0.0, 1.0) * 3.0
        return NodeState(flood_m=self._flood.copy(), depth_m=depth.astype(np.float32))

    def forecast(self, rain_mm_hr: float, capacity: Optional[np.ndarray], steps: list[int]) -> dict[int, np.ndarray]:
        f = self._flood.copy()
        wanted = set(steps)
        out: dict[int, np.ndarray] = {}
        for k in range(1, max(steps) + 1):
            f = self._advance(f, float(rain_mm_hr))
            if k in wanted:
                out[k] = f.copy()
        return out
