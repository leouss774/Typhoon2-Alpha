from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LatLng(BaseModel):
    lat: float
    lon: float


class ZoneAssessRequest(BaseModel):
    mode: str = Field(..., pattern="^(single|multi)$")
    points: list[LatLng] = Field(default_factory=list)
    polygon: list[LatLng] = Field(default_factory=list)
    address: str | None = None


class HazardInfo(BaseModel):
    hazard: str
    label: str
    level: str | None = None
    score: float | None = None


class SourceStatus(BaseModel):
    source: str
    ok: bool
    error: str | None = None


class BuildingHazardSummary(BaseModel):
    address_label: str | None = None
    lat: float
    lon: float
    hazards: list[HazardInfo] = Field(default_factory=list)
    catnat_total: int = 0
    distance_cours_eau_m: float | None = None
    distance_foret_m: float | None = None
    bdnb_cle_interop_adr: str | None = None
    bdnb_geom: dict | None = None
    source: str = "live"
    source_errors: list[SourceStatus] = Field(default_factory=list)
    data_quality: str = "ok"
    score_global: float | None = None


class HazardBreakdown(BaseModel):
    hazard: str
    label: str
    present_count: int = 0
    total_count: int = 0
    pct_present: float = 0.0
    levels: list[str] = Field(default_factory=list)
    mean_score: float | None = None
    max_score: float | None = None


class CatnatTotals(BaseModel):
    inondation: int = 0
    secheresse: int = 0
    mouvement_terrain: int = 0
    total: int = 0


class ZoneReport(BaseModel):
    address: str
    nb_points: int
    nb_ok: int
    nb_errors: int
    hazard_breakdown: list[HazardBreakdown]
    catnat_totals: CatnatTotals = Field(default_factory=CatnatTotals)
    buildings: list[BuildingHazardSummary] = Field(default_factory=list)
    narrative: str = ""
    recommendations: list[str] = Field(default_factory=list)
    enumeration_method: str
    duration_seconds: float
    aggregate_score: float | None = None
    aggregate_tier: str | None = None
    narrative_source: str = "template"
    data_sources_ok: list[str] = Field(default_factory=list)
    report_schema_version: str = "1.0"
    export_v2: dict[str, Any] | None = None

