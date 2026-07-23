"""Modèle du rapport d'analyse complet."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from backend.models.bien import BienImmobilier
from backend.models.risque import AnalyseRisques
from backend.agent_graph.state import TravauxRecommandation


class RapportAnalyse(BaseModel):
    """Rapport d'analyse de risque complet pour un bien."""

    session_id: str = Field(description="Identifiant unique")
    date_creation: datetime = Field(default_factory=datetime.now)
    bien: BienImmobilier
    analyse_risques: AnalyseRisques
    recommandations: list[TravauxRecommandation]
    projection_2050: dict[str, float] = Field(default_factory=dict)
    synthese_executive: str = Field(description="Synthèse pour le client")
    cout_total_bas: float = Field(default=0, description="Coût total estimé bas (€)")
    cout_total_haut: float = Field(default=0, description="Coût total estimé haut (€)")
    gain_resilience_moyen: float = Field(default=0, description="Gain de résilience moyen (%)")
