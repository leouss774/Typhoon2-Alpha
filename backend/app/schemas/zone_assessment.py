"""
Schémas Pydantic pour l'API d'évaluation de zone (Promoteurs Immobiliers).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ZoneBounds(BaseModel):
    """Limites rectangulaires d'une zone."""
    lat_min: float = Field(..., ge=-90, le=90)
    lon_min: float = Field(..., ge=-180, le=180)
    lat_max: float = Field(..., ge=-90, le=90)
    lon_max: float = Field(..., ge=-180, le=180)


class ZoneAssessmentRequest(BaseModel):
    """Requête d'évaluation de zone."""
    zone: ZoneBounds
    spacing_km: float = Field(default=0.5, ge=0.1, le=5.0, description="Espacement entre points (km)")
    max_points: int = Field(default=50, ge=1, le=200, description="Nombre max de points d'échantillonnage")
    max_concurrency: int = Field(default=5, ge=1, le=20, description="Appels simultanés max")
    land_only: bool = Field(default=False, description="Mode terrain nu (sans BDNB)")
    include_samples: bool = Field(default=False, description="Inclure les résultats détaillés par point")


class PerilDistribution(BaseModel):
    """Distribution des scores pour un péril."""
    min_score: float
    max_score: float
    moyenne: float
    mediane: float
    ecart_type: float
    pct_faible: float
    pct_modere: float
    pct_eleve: float
    pct_critique: float
    worst_case: float


class PromoteurReportSchema(BaseModel):
    """3 champs spécifiques au cas d'usage Promoteur Immobilier (Person 3)."""
    faisabilite_construction: str = "Non disponible"
    impact_valeur_fonciere: str = "Non disponible"
    perspective_assurabilite: str = "Non disponible"
    notes: list[str] = []


class ZoneAssessmentResponse(BaseModel):
    """Réponse d'évaluation de zone."""
    status: str = "ok"
    zone: ZoneBounds
    nb_points: int
    nb_points_valides: int = 0
    nb_points_erreur: int = 0
    score_moyen: float = 0.0
    score_pondere: float = 0.0
    rating_global: str = "Non évaluable"
    land_only: bool = False
    worst_case_peril: str | None = None
    worst_case_score: float | None = None
    perils: dict[str, PerilDistribution] = {}
    duree_evaluation_s: float | None = None
    points_echantillon: list[dict] | None = None
    message: str | None = None
    rapport_promoteur: PromoteurReportSchema | None = None
