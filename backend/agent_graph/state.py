"""Etat partage du graphe LangGraph Typhoon.

Flux :
  1. collect_georisques  → appel API Georisques via risk_score_pipeline
  2. generate_recommandations → merge Georisques + formulaire → recommandations par zone
  3. assemble_output     → construction du JSON final pour le jumeau numerique

Chaque noeud lit et ecrit dans le State via les cles definies ci-dessous.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class TyphoonState(BaseModel):
    """State unique partage par tous les noeuds du graphe LangGraph."""

    # ── Entree ──────────────────────────────────
    session_id: str = Field(default="", description="Identifiant unique de session")
    client_form: dict[str, Any] = Field(
        default_factory=dict,
        description="Donnees du formulaire client (adresse, type bien, surface, etc.)",
    )
    raw_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Donnees brutes supplementaires (optionnel)",
    )

    # ── Etape 1 : Collecte Georisques ───────────
    georisques_data: Optional[dict[str, Any]] = Field(
        default=None,
        description="Donnees collectees via risk_score_pipeline.analyser_adresse()",
    )
    collect_error: Optional[str] = Field(
        default=None,
        description="Message d'erreur si la collecte Georisques a echoue",
    )

    # ── Etape 2 : Recommandations par zone ──────
    zone_recommandations: Optional[dict[str, Any]] = Field(
        default=None,
        description="Recommandations generees par generate_zone_recommendations()",
    )

    # ── Etape 3 : JSON final ────────────────────
    final_json: Optional[dict[str, Any]] = Field(
        default=None,
        description="JSON final complet au format assessment_complet.json, pret pour le jumeau numerique",
    )

    # ── Routage interne ─────────────────────────
    next_node: str = Field(default="collect_georisques")
    errors: list[str] = Field(default_factory=list)
