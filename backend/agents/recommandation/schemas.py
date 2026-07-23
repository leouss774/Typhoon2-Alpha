from __future__ import annotations

from pydantic import BaseModel, Field


class RecommandationInput(BaseModel):
    """Données d'entrée pour la génération de recommandations."""

    risques_dominants: list[str] = Field(description="Codes des risques dominants")
    scores_par_alea: dict[str, float] = Field(description="Scores par aléa")
    type_bien: str = Field(description="Type de bien")
    annee_construction: int = Field(description="Année de construction")
    materiau_principal: str = Field(description="Matériau principal")
    surface_m2: float = Field(description="Surface en m²")
    budget_max: float | None = Field(default=None, description="Budget maximum (€)")


class TravauxOutput(BaseModel):
    """Une recommandation de travaux structurée."""

    priorite: int = Field(ge=1, le=5)
    titre: str
    description: str
    cout_estime_bas: float
    cout_estime_haut: float
    gain_resilience_pct: float = Field(ge=0.0, le=100.0)
    aleas_adresses: list[str]


class RecommandationOutput(BaseModel):
    """Sortie complète des recommandations."""

    recommandations: list[TravauxOutput]
    cout_total_bas: float
    cout_total_haut: float
    gain_moyen: float
