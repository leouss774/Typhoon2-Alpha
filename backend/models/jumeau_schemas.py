"""
jumeau_schemas.py
-----------------
Schémas Pydantic qui formalisent le contrat JSON attendu par
`jumeau_numerique.html.j2` (voir commentaire en tête du <script> côté HTML).
Ce contrat NE CHANGE PAS : c'est celui déjà utilisé par le mock JS
(MOCK_DATA). Tout ce que produisent Mistral ou le risk engine doit être
validé contre ces classes avant d'être injecté dans le template ou renvoyé
en JSON à l'API.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

ZONE_NAMES = [
    "fondations",
    "murs_nord",
    "murs_sud",
    "murs_est",
    "murs_ouest",
    "toiture",
    "sous_sol",
]

NiveauRisque = Literal["faible", "modere", "eleve", "critique"]


def niveau_from_score(score: float) -> NiveauRisque:
    """Même mapping score -> couleur/niveau que scoreToColor() côté JS (garder synchronisé)."""
    if score < 30:
        return "faible"
    if score < 60:
        return "modere"
    if score < 80:
        return "eleve"
    return "critique"


class Recommandation(BaseModel):
    travaux: str
    cout_estime: str  # ex: "9000-16000€" (fourchette texte, fournie par l'Agent Recommandation RAG)
    gain_resilience: int = Field(ge=0, le=100)


class ZoneRisque(BaseModel):
    risque: int = Field(ge=0, le=100)
    niveau: NiveauRisque
    alea_principal: str
    justification: str
    recommandations: list[Recommandation] = Field(default_factory=list)

    @field_validator("justification")
    @classmethod
    def justification_courte(cls, v: str) -> str:
        # Le panneau latéral est prévu pour un texte court (voir #info-justif en CSS)
        if len(v) > 400:
            return v[:397] + "..."
        return v


class ZonesDataset(BaseModel):
    """Un jeu complet de zones pour une année donnée (2025 ou 2050)."""

    model_config = {"extra": "forbid"}

    fondations: ZoneRisque
    murs_nord: ZoneRisque
    murs_sud: ZoneRisque
    murs_est: ZoneRisque
    murs_ouest: ZoneRisque
    toiture: ZoneRisque
    sous_sol: ZoneRisque

    def as_zone_dict(self) -> dict[str, ZoneRisque]:
        return {name: getattr(self, name) for name in ZONE_NAMES}


class ProjectionDataset(BaseModel):
    score_global: int = Field(ge=0, le=100)
    zones: ZonesDataset


class JumeauPayload(BaseModel):
    """Le JSON complet injecté dans le template / consommé par window.MaisonAPI.loadFullDataset()."""

    score_global: int = Field(ge=0, le=100)
    zones: ZonesDataset
    projection_2050: ProjectionDataset | None = None

    # Métadonnées utiles au template mais hors contrat JS strict (le JS ignore
    # les clés qu'il ne connaît pas, donc les ajouter ici est sans risque).
    adresse: str | None = None
    geometrie: dict | None = None  # sortie de geometry_service.compute_house_footprint


class VulnerabilityTestResult(BaseModel):
    """Sortie attendue de l'appel Mistral 'test de vulnérabilité' (déclenché au clic sur une zone)."""

    model_config = {"extra": "forbid"}

    zone: str
    scenario: str  # ex: "Sécheresse de 6 semaines suivie d'un épisode pluvieux intense"
    score_avant: int = Field(ge=0, le=100)
    score_apres_travaux: int = Field(ge=0, le=100)
    resume: str
    points_de_vigilance: list[str] = Field(default_factory=list)

    @field_validator("zone")
    @classmethod
    def zone_connue(cls, v: str) -> str:
        if v not in ZONE_NAMES:
            raise ValueError(f"zone inconnue: {v} (attendu: {ZONE_NAMES})")
        return v
