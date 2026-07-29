"""
Pydantic models for the zone-insurer async job workflow.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float
    lon: float


class ZoneAssessRequest(BaseModel):
    """New endpoint: define zone by mode + points or polygon."""
    mode: str = Field(..., pattern="^(single|multi)$", description="single=un point, multi=polygone")
    points: list[LatLng] = Field(default_factory=list, description="Points sélectionnés (mode multi)")
    polygon: list[LatLng] = Field(default_factory=list, description="Sommets du polygone (mode multi)")
    address: str | None = Field(default=None, description="Adresse pour le mode single")


class ZoneJobRequest(BaseModel):
    address: str = Field(..., min_length=3, description="Adresse ou point central de la zone")
    radius_m: float = Field(default=300.0, ge=50.0, le=1500.0, description="Rayon en metres")


class JobAccepted(BaseModel):
    job_id: str
    status: str = "processing"


class BuildingRiskSummary(BaseModel):
    address_label: str | None
    lat: float
    lon: float
    score_global: float
    tier: str
    worst_peril: str | None = None
    flagged_for_review: bool = False
    source: str  # "live" | "cache"
    catnat: dict[str, int] = Field(default_factory=dict)
    distance_cours_eau_m: float | None = None
    distance_foret_m: float | None = None


class HazardBreakdown(BaseModel):
    hazard: str
    min_score: float
    max_score: float
    mean_score: float
    pct_high_or_critical: float


class ZoneReport(BaseModel):
    address: str
    radius_m: float
    nb_buildings: int
    nb_ok: int
    nb_errors: int
    aggregate_score: float
    aggregate_tier: str
    hazard_breakdown: list[HazardBreakdown]
    flagged_buildings: list[BuildingRiskSummary]
    all_buildings: list[BuildingRiskSummary]
    catnat_totals: dict[str, int] = Field(default_factory=dict)
    financial_context: dict[str, Any] | None = None
    climate_projection: dict[str, Any] | None = None
    narrative: str = ""
    recommendations: list[str]
    enumeration_method: str
    duration_seconds: float


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # processing | done | error
    current_step: str
    total_buildings: int
    processed_buildings: int
    result: ZoneReport | None = None
    error: str | None = None
