"""digital_twin_agent — dernier maillon du graphe.

Assemble la géométrie, les scores et l'adresse dans le contrat JSON
consommé par la scène Three.js du frontend.
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.digital_twin.geometry_builder import build_geometry_from_bdnb

logger = get_logger(__name__)


def _apply_mvp_defaults(geometry: dict[str, Any], annee_construction: int | None) -> None:
    if geometry.get("has_basement") is None:
        geometry["has_basement"] = bool(annee_construction and annee_construction < 1949)
    if geometry.get("has_cellar") is None:
        geometry["has_cellar"] = False
    if geometry.get("has_garage") is None:
        geometry["has_garage"] = False
    if geometry.get("has_garden") is None:
        geometry["has_garden"] = False


def _bien_type(bdnb: dict[str, Any] | None) -> str:
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else None
    usage = (batiment or {}).get("usage_niveau_1_txt") if isinstance(batiment, dict) else None
    return usage or "maison individuelle"


def assemble_contract(
    building_data: dict[str, Any],
    risk_result: dict[str, Any],
    formulaire: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble le contrat final pour le frontend."""
    logger.info("digital_twin_agent -- assemblage du contrat")

    adresse_info = building_data.get("adresse") or {}
    bdnb = building_data.get("bdnb")
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else {}
    batiment = batiment or {}

    geometry_report = build_geometry_from_bdnb(batiment, formulaire=formulaire)
    geometry = geometry_report["geometry"]
    annee_construction = batiment.get("annee_construction")
    _apply_mvp_defaults(geometry, annee_construction)

    climat_open_meteo = building_data.get("climat_open_meteo") or {}
    projection = climat_open_meteo.get("projection_2041_2050") or {}
    reference = climat_open_meteo.get("reference_2015_2024") or {}

    contract = {
        "adresse": adresse_info.get("label", ""),
        "bien": {
            "type": _bien_type(bdnb),
            "annee_construction": annee_construction,
            "coordonnees": {"lat": adresse_info.get("lat"), "lon": adresse_info.get("lon")},
        },
        "geometry": geometry,
        "score_global": risk_result["score_global"],
        "zones": risk_result["zones"],
        "projection_2050": risk_result["projection_2050"],
        "climat": {
            "2050": {
                "temperature_max_projetee_c": projection.get("temperature_max_absolue_c") or projection.get("temperature_max_moyenne_c"),
                "temperature_max_moyenne_c": projection.get("temperature_max_moyenne_c"),
                "precipitation_annuelle_moyenne_mm": projection.get("precipitation_annuelle_moyenne_mm"),
                "jours_chaleur_extreme_par_an": projection.get("jours_chaleur_extreme_par_an"),
            },
            "reference_2015_2024": {
                "temperature_max_absolue_c": reference.get("temperature_max_absolue_c"),
                "temperature_max_moyenne_c": reference.get("temperature_max_moyenne_c"),
                "precipitation_annuelle_moyenne_mm": reference.get("precipitation_annuelle_moyenne_mm"),
                "jours_chaleur_extreme_par_an": reference.get("jours_chaleur_extreme_par_an"),
            },
            "source": "Open-Meteo Climate API",
        },
        "marche": {
            "dvf_disponible": bool(building_data.get("dvf_local")),
        },
        "_sources": {
            "climat_open_meteo": bool(climat_open_meteo),
            "climat_copernicus": bool(building_data.get("climat_copernicus")),
            "dvf_local": bool(building_data.get("dvf_local")),
        },
        "_erreurs_collecte": building_data.get("erreurs", []),
    }

    logger.info(
        "  -> contrat prêt : score_global=%d, %d zone(s)",
        contract["score_global"],
        len(contract["zones"]),
    )
    return contract
