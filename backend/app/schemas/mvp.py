from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float
    lon: float


class MvpRequest(BaseModel):
    mode: str = Field(default="single", pattern="^(single|multi)$", description="single=un bâtiment, multi=polygone")
    address: str | None = Field(default=None, description="Adresse (mode single)")
    points: list[LatLng] = Field(default_factory=list, description="Points (mode multi)")
    polygon: list[LatLng] = Field(default_factory=list, description="Sommets du polygone (mode multi)")


class MvpBuildingSummary(BaseModel):
    address_label: str | None = None
    lat: float
    lon: float
    score_global: float
    tier: str
    worst_peril: str | None = None


class MvpHazardBreakdown(BaseModel):
    hazard: str
    min_score: float
    max_score: float
    mean_score: float
    pct_high_or_critical: float


class MvpResponse(BaseModel):
    address: str
    score_global: float
    tier: str
    hazard_breakdown: list[MvpHazardBreakdown]
    all_buildings: list[MvpBuildingSummary]
    flagged_buildings: list[MvpBuildingSummary]
    nb_buildings: int
    nb_ok: int
    nb_errors: int
    recommendations: list[str]
    enumeration_method: str
    duration_seconds: float
