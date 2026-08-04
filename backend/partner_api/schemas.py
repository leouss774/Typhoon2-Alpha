"""
Contrats Pydantic de la Typhoon Partner API.

Volontairement distincts des dicts internes de `app.scoring.risk_model` :
ce module est le contrat public versionne consomme par les projets tiers,
il ne doit pas bouger juste parce qu'un champ interne de tracability
(_sources, _f_score, _v_score...) change cote moteur de scoring. La
traduction dict interne -> ce schema se fait dans `service.py`.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    address: str = Field(..., min_length=3, description="Adresse postale complete du bien a analyser")


class Address(BaseModel):
    input: str = Field(..., description="Adresse telle qu'envoyee dans la requete")
    label: str = Field(..., description="Adresse normalisee par le geocodeur")
    citycode: str
    postcode: str
    city: str
    lat: float
    lon: float


class Confidence(BaseModel):
    score: int = Field(..., description="0-100, independant du score de risque")
    niveau: str
    n_sources_disponibles: int
    n_sources_total: int


class Zone(BaseModel):
    risque: int = Field(..., description="0-100")
    niveau: str
    alea_principal: str
    justification: str
    recommandations: list[dict[str, Any]] = Field(default_factory=list)


class Hazard(BaseModel):
    label: str
    risque: int
    niveau: str
    justification: str


class RiskPeriod(BaseModel):
    score_global: int
    niveau_global: str
    zones: dict[str, Zone]
    risques_par_alea: dict[str, Hazard]


class AnalyzeResponse(BaseModel):
    adresse: Address
    score_global: int
    niveau_global: str
    confidence: Confidence
    zones: dict[str, Zone]
    risques_par_alea: dict[str, Hazard]
    projection_2050: RiskPeriod
    erreurs_sources: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Sources de collecte en erreur ou indisponibles pour cette adresse (ne bloque pas l'analyse)",
    )
    genere_le: str
