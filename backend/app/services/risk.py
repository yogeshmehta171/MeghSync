"""
Pure functions (no I/O) that turn model numbers into the labels the frontend shows.
Thresholds are runtime-configurable (config table) and passed in; nothing here is hard-coded to one place.
"""
from __future__ import annotations

from typing import Mapping

LEVELS = ["SAFE", "LOW", "MODERATE", "HIGH", "CRITICAL"]          # alert levels (spec)
LEVEL_RANK = {name: i for i, name in enumerate(LEVELS)}
RISK_LABEL = {"SAFE": "Safe", "LOW": "Low", "MODERATE": "Moderate", "HIGH": "High", "CRITICAL": "Critical"}

# Surface-flood depth thresholds in metres. `route_block_m` MUST equal what routing treats as impassable.
DEFAULT_THRESHOLDS: dict[str, float] = {
    "low_m": 0.03,        # any visible water
    "moderate_m": 0.15,   # also the route-blocking depth
    "high_m": 0.30,
    "critical_m": 0.60,
    "route_block_m": 0.15,
}


def validate_thresholds(t: Mapping[str, float]) -> dict[str, float]:
    keys = ("low_m", "moderate_m", "high_m", "critical_m", "route_block_m")
    out = {}
    for k in keys:
        if k not in t:
            raise ValueError(f"missing threshold '{k}'")
        v = float(t[k])
        if not (0.0 < v <= 5.0):
            raise ValueError(f"threshold '{k}' must be between 0 and 5 metres")
        out[k] = v
    if not (out["low_m"] < out["moderate_m"] < out["high_m"] < out["critical_m"]):
        raise ValueError("thresholds must increase: low < moderate < high < critical")
    return out


def level_for_depth(flood_m: float, t: Mapping[str, float]) -> str:
    if flood_m >= t["critical_m"]:
        return "CRITICAL"
    if flood_m >= t["high_m"]:
        return "HIGH"
    if flood_m >= t["moderate_m"]:
        return "MODERATE"
    if flood_m >= t["low_m"]:
        return "LOW"
    return "SAFE"


def node_state(flood_m: float, depth_m: float, max_depth_m: float, t: Mapping[str, float]) -> str:
    """The five hydraulic states of the spec."""
    if flood_m >= t["critical_m"]:
        return "SEVERE"
    if flood_m >= t["route_block_m"]:
        return "SURFACE_FLOODING"
    pipe_full = max_depth_m > 0 and depth_m >= 0.95 * max_depth_m
    if flood_m >= t["low_m"] or pipe_full:
        return "SURCHARGE"
    if max_depth_m > 0 and depth_m >= 0.5 * max_depth_m:
        return "INCREASED_LEVEL"
    return "NORMAL"


def frontend_status(state: str) -> str:
    """Collapse the 5 states into the 3 values the current frontend type knows."""
    if state in ("SEVERE", "SURFACE_FLOODING"):
        return "FLOODED"
    if state == "SURCHARGE":
        return "SURCHARGE"
    return "PASSABLE"


_ACTIONS = {
    "CRITICAL": "Deploy pump and divert traffic",
    "HIGH": "Dispatch inspection team; prepare pump",
    "MODERATE": "Monitor closely; consider blocking",
    "LOW": "Monitor",
    "SAFE": "None",
}


def suggested_action(level: str, state: str, blocked: bool) -> str:
    if blocked:
        return "Blocked by municipality; clear and re-open when safe"
    if state == "SURCHARGE" and level in ("SAFE", "LOW"):
        return "Check drain for blockage"
    return _ACTIONS[level]
