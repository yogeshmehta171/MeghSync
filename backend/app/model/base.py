"""
The one interface the rest of the backend uses to talk to ANY flood model.
To plug in the next retrained model: change the checkpoint, or write a new provider with these 4 members.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

import numpy as np

SEQ_LEN = 12                      # model input window (steps)
STEP_MINUTES = 5                  # one model step = 5 minutes of simulated time

# (label, hours, model steps, confidence). Steps are counted from the state returned by step().
FORECAST_HORIZONS = [
    {"label": "+30 min", "hours": 0.5, "steps": 6,  "confidence": "moderate"},
    {"label": "+1 h",    "hours": 1.0, "steps": 12, "confidence": "low"},
    {"label": "+2 h",    "hours": 2.0, "steps": 24, "confidence": "trend_only"},
    {"label": "+3 h",    "hours": 3.0, "steps": 36, "confidence": "trend_only"},
]


@dataclass
class NodeState:
    flood_m: np.ndarray   # [N] surface flood depth, metres
    depth_m: np.ndarray   # [N] water depth in the node, metres


class ModelProvider(Protocol):
    name: str                 # "gnn" | "mock" -- shown to clients so nobody mistakes mock data for real
    version: str
    n_nodes: int
    n_edges: int              # number of blockable drain edges the model understands (0 if unused)

    def reset(self) -> None: ...

    def step(self, rain_mm_hr: float, capacity: Optional[np.ndarray]) -> NodeState:
        """Advance the live state by one 5-minute step. capacity: [E] pipe capacity 0..1 or None (all clear)."""

    def forecast(self, rain_mm_hr: float, capacity: Optional[np.ndarray], steps: list[int]) -> dict[int, np.ndarray]:
        """Roll forward from the current state WITHOUT changing it, assuming rain stays at rain_mm_hr.
        Returns {steps: flood_m[N]} for each requested step count."""
