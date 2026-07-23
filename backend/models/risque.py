"""Modèles liés aux risques et aléas naturels."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AledaRisque(BaseModel):
    """Un aléa naturel avec son score et niveau."""

    code: str = Field(description="Identifiant (rga, inondation, etc.)")
    label: str = Field(description="Nom complet")
    score: float = Field(ge=0.0, le=100.0)
    niveau: str = Field(description="faible | modéré | élevé | critique")
    poids: float = Field(default=1.0, ge=0.0, description="Poids dans le calcul global")
    projection_2050: float | None = Field(default=None, description="Score projeté en 2050")


class AnalyseRisques(BaseModel):
    """Analyse complète des risques d'un bien."""

    score_global: float = Field(ge=0.0, le=100.0)
    niveau_global: str = Field(description="Niveau global")
    aleas: list[AledaRisque]
    risques_dominants: list[AledaRisque] = Field(description="Top 3 des risques")
    synthese: str = Field(description="Synthèse de l'analyse")
