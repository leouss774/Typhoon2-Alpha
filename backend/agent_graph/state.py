"""Schéma d'état partagé du graphe LangGraph.

Ce state transite à travers tous les nœuds du graphe et s'enrichit
à chaque étape : score → analyse LLM → recommandations RAG → rapport.
"""

from __future__ import annotations

from typing import Annotated, Optional

from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class AleaScore(BaseModel):
    """Score déterministe pour un aléa spécifique."""

    code: str = Field(description="Identifiant de l'aléa (ex: rga, inondation)")
    label: str = Field(description="Nom lisible de l'aléa")
    score: float = Field(ge=0.0, le=100.0, description="Score de risque (0 = aucun, 100 = critique)")
    niveau: str = Field(description="Niveau de risque: faible | modéré | élevé | critique")


class AnalyseRisque(BaseModel):
    """Rapport structuré retourné par l'Agent Analyste Risque (Claude)."""

    scores_par_alea: list[AleaScore] = Field(description="Scores qualitatifs par aléa")
    risques_dominants: list[str] = Field(description="Top 3 des risques dominants")
    justifications: dict[str, str] = Field(description="Justification courte par aléa")
    synthese: str = Field(description="Synthèse globale de l'analyse")


class TravauxRecommandation(BaseModel):
    """Une recommandation de travaux avec estimation."""

    priorite: int = Field(ge=1, le=5, description="Priorité (1 = urgente, 5 = optionnelle)")
    titre: str = Field(description="Nom du travail (ex: Renforcement fondations)")
    description: str = Field(description="Description détaillée")
    cout_estime_bas: float = Field(description="Coût estimé bas (€)")
    cout_estime_haut: float = Field(description="Coût estimé haut (€)")
    gain_resilience_pct: float = Field(ge=0.0, le=100.0, description="Gain de résilience estimé (%)")
    aleas_adresses: list[str] = Field(description="Aléas atténués par ces travaux")


class RapportFinal(BaseModel):
    """Rapport d'analyse complet assemblé par le générateur."""

    score_global: float = Field(ge=0.0, le=100.0, description="Score global de risque")
    analyse_risque: AnalyseRisque
    recommandations: list[TravauxRecommandation]
    projection_2050: dict[str, float] = Field(description="Projection des scores en 2050")
    synthese_executive: str = Field(description="Synthèse pour le client")


class TyphoonState(BaseModel):
    """State unique partagé par tous les nœuds du graphe LangGraph."""

    # ── Entrée ──────────────────────────────────
    session_id: str = Field(default="", description="Identifiant unique de session")
    client_form: dict = Field(default_factory=dict, description="Données du formulaire client")
    raw_data: dict = Field(default_factory=dict, description="Données brutes (DRIAS, géocodage, etc.)")

    # ── Étape 1 : Score déterministe ────────────
    score_global: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    scores_par_alea: dict[str, float] = Field(default_factory=dict)

    # ── Étape 2 : Analyse LLM (Agent #1) ────────
    analyse_risque: Optional[AnalyseRisque] = Field(default=None)

    # ── Étape 3 : Recommandations RAG (Agent #2) ─
    recommandations: list[TravauxRecommandation] = Field(default_factory=list)

    # ── Étape 4 : Rapport final ──────────────────
    rapport_final: Optional[RapportFinal] = Field(default=None)

    # ── Validation ───────────────────────────────
    validation_errors: list[str] = Field(default_factory=list)
    validation_passed: bool = Field(default=False)

    # ── Chat (Agent #3) ──────────────────────────
    messages: Annotated[list, add_messages] = Field(default_factory=list)

    # ── Routage interne ─────────────────────────
    next_node: str = Field(default="calculate_score")
