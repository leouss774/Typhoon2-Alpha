"""
Orchestration de la Typhoon Partner API.

Reutilise directement les agents internes (collector_agent, scoring_agent,
recommandations_agent) plutot que de dupliquer la logique de collecte/scoring :
ce service est une nouvelle facade autour du meme moteur, pas une
reimplementation. digital_twin_agent / interpretation_agent (geometrie 3D,
conclusion redigee) sont volontairement exclus : hors perimetre pour un
partenaire qui veut un score de risque exploitable par API, pas une scene
Three.js.
"""

from __future__ import annotations

from typing import Any

from app.agents import recommandations_agent, scoring_agent
from app.agents.collector_agent import collect
from app.connectors.geocoding import GeocodingError
from app.core.config import settings
from app.core.logging import get_logger
from app.scoring.risk_model import _niveau

from partner_api.schemas import (
    Address,
    AnalyzeResponse,
    Confidence,
    Hazard,
    RiskPeriod,
    Zone,
)

logger = get_logger(__name__)


class AddressNotFound(Exception):
    """L'adresse fournie n'a pas pu etre geocodee."""


def _zone_from_raw(raw: dict[str, Any]) -> Zone:
    return Zone(
        risque=raw["risque"],
        niveau=raw["niveau"],
        alea_principal=raw["alea_principal"],
        justification=raw["justification"],
        recommandations=raw.get("recommandations", []),
    )


def _hazard_from_raw(raw: dict[str, Any]) -> Hazard:
    return Hazard(
        label=raw["label"],
        risque=raw["risque"],
        niveau=raw["niveau"],
        justification=raw["justification"],
    )


def _period_from_raw(score_global: int, zones_raw: dict[str, Any], hazards_raw: dict[str, Any]) -> RiskPeriod:
    return RiskPeriod(
        score_global=score_global,
        niveau_global=_niveau(score_global),
        zones={name: _zone_from_raw(z) for name, z in zones_raw.items()},
        risques_par_alea={name: _hazard_from_raw(h) for name, h in hazards_raw.items()},
    )


async def analyze_address(address: str) -> AnalyzeResponse:
    """Point d'entree unique de la Partner API : adresse -> risque + recommandations.

    Leve AddressNotFound si l'adresse ne peut pas etre geocodee (entree
    invalide, 422 cote route). Toute autre erreur individuelle de source
    (Georisques, BDNB...) ne fait pas echouer l'appel : elle reste
    consignee dans building_data["erreurs"] et le score est calcule avec
    les sources disponibles, comme dans /diagnostic.
    """
    logger.info("partner_api.analyze_address -- adresse=%r", address)

    try:
        building_data = await collect(address, enable_copernicus=settings.copernicus_enabled)
    except GeocodingError as exc:
        raise AddressNotFound(str(exc)) from exc

    state: dict[str, Any] = {"building_data": building_data, "formulaire": None}
    state.update(scoring_agent.run(state))
    state.update(await recommandations_agent.run(state))

    risk_scores = state["risk_scores"]
    adresse_info = building_data.get("adresse") or {}

    return AnalyzeResponse(
        adresse=Address(
            input=address,
            label=adresse_info.get("label", address),
            citycode=adresse_info.get("citycode", ""),
            postcode=adresse_info.get("postcode", ""),
            city=adresse_info.get("city", ""),
            lat=adresse_info.get("lat"),
            lon=adresse_info.get("lon"),
        ),
        score_global=risk_scores["score_global"],
        niveau_global=_niveau(risk_scores["score_global"]),
        confidence=Confidence(
            score=risk_scores["confidence"]["score"],
            niveau=risk_scores["confidence"]["niveau"],
            n_sources_disponibles=risk_scores["confidence"]["n_sources_disponibles"],
            n_sources_total=risk_scores["confidence"]["n_sources_total"],
        ),
        zones={name: _zone_from_raw(z) for name, z in risk_scores["zones"].items()},
        risques_par_alea={name: _hazard_from_raw(h) for name, h in risk_scores["risques_par_alea"].items()},
        projection_2050=_period_from_raw(
            risk_scores["projection_2050"]["score_global"],
            risk_scores["projection_2050"]["zones"],
            risk_scores["projection_2050"]["risques_par_alea"],
        ),
        erreurs_sources=building_data.get("erreurs", []),
        genere_le=building_data.get("genere_le", ""),
    )
