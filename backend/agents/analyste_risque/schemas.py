"""Schémas d'entrée/sortie pour l'Agent Analyste Risque.

L'agent reçoit des données structurées et retourne
un JSON validé par Pydantic.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyseRisqueInput(BaseModel):
    """Données d'entrée pour l'analyse des risques."""

    adresse: str = Field(description="Adresse complète du bien")
    type_bien: str = Field(description="Type de bien: maison | appartement")
    surface_m2: float = Field(description="Surface habitable en m²")
    annee_construction: int = Field(description="Année de construction")
    etage: int | None = Field(default=None, description="Étage (si appartement)")
    sous_sol: bool = Field(default=False, description="Présence d'un sous-sol")
    materiau_principal: str = Field(description="Matériau principal: brique | parpaing | bois | pierre")
    score_global: float = Field(ge=0.0, le=100.0, description="Score global déterministe")
    scores_par_alea: dict[str, float] = Field(description="Scores par aléa")


class ScoreAleaOutput(BaseModel):
    """Score qualitatif pour un aléa."""

    code: str = Field(description="Code de l'aléa")
    label: str = Field(description="Nom de l'aléa")
    score: float = Field(ge=0.0, le=100.0, description="Score")
    niveau: str = Field(description="Niveau: faible | modéré | élevé | critique")
    justification: str = Field(description="Justification courte (2-3 phrases)")


class AnalyseRisqueOutput(BaseModel):
    """Sortie structurée de l'analyse LLM."""

    scores_par_alea: list[ScoreAleaOutput]
    risques_dominants: list[str] = Field(description="Top 3 des risques", max_length=3)
    synthese: str = Field(description="Synthèse globale (max 500 caractères)")
