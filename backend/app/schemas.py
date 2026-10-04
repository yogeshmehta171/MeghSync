from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    municipality_id: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=256)


class Coordinate(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class RouteRequest(BaseModel):
    start: Coordinate
    destination: Coordinate


class ReportCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    phone: str = Field(..., min_length=7, max_length=20)
    location: str = Field(..., min_length=3, max_length=200)
    description: str = Field(..., min_length=3, max_length=1000)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)


class ReviewRequest(BaseModel):
    node_id: Optional[str] = Field(None, max_length=64)      # approve only: overrides the automatic match
    note: Optional[str] = Field(None, max_length=500)


class MeasuresRequest(BaseModel):
    measures: str = Field('', max_length=1000)           # empty text clears the measures


class RainRequest(BaseModel):
    rain_mm_hr: float = Field(..., ge=0, le=500)


class ResetRequest(BaseModel):
    clear_blocks: bool = False


class BlockCreate(BaseModel):
    node_id: Optional[str] = Field(None, max_length=64)
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lon: Optional[float] = Field(None, ge=-180, le=180)
    note: Optional[str] = Field(None, max_length=500)


class ConfigUpdate(BaseModel):
    changes: dict[str, Any] = Field(..., min_length=1)


class PipeCapacity(BaseModel):
    edge_idx: int = Field(..., ge=0)
    capacity_fraction: float = Field(..., ge=0.1, le=1.0)


class PipeCapacityRequest(BaseModel):
    blockages: list[PipeCapacity] = Field(..., min_length=1)
    replace: bool = False
