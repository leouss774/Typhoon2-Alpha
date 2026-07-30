"""digital_twin_agent — dernier maillon du graphe.

Assemble la géométrie, les scores et l'adresse dans le contrat JSON
consommé par la scène Three.js du frontend.
"""

from __future__ import annotations

import os
import sys
from typing import Any

from app.core.logging import get_logger
from app.digital_twin.geometry_builder import build_geometry_from_bdnb

# ── Import robuste du générateur de recommandations ────────────────────────────
# Le générateur est dans backend/api/recommandations_generator.py.
# Selon le point d'entrée (backend/main.py vs app/main.py), le sys.path
# peut contenir la racine du projet ou le dossier backend/.
# On essaie tous les chemins possibles.

_HAS_RECO_GENERATOR = False
_generate_zone_recommendations = None

# 1) Chemin absolu : on ajoute backend/ au sys.path si pas déjà présent
_backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
_backend_path = os.path.normpath(_backend_path)
if _backend_path not in sys.path:
    sys.path.insert(0, _backend_path)

# 2) Tentatives d'import
try:
    from api.recommandations_generator import generate_zone_recommendations as _gen
    _HAS_RECO_GENERATOR = True
    _generate_zone_recommendations = _gen
except ImportError:
    try:
        from backend.api.recommandations_generator import generate_zone_recommendations as _gen
        _HAS_RECO_GENERATOR = True
        _generate_zone_recommendations = _gen
    except ImportError:
        _HAS_RECO_GENERATOR = False
        _generate_zone_recommendations = None

logger = get_logger(__name__)
logger.info(
    "digital_twin_agent -- générateur recommandations: %s (sys.path=%s)",
    "disponible" if _HAS_RECO_GENERATOR else "INDISPONIBLE",
    _backend_path,
)

logger = get_logger(__name__)


def _normaliser_georisques(georisques: dict[str, Any]) -> dict[str, Any]:
    """Normalise les données Georisques du collecteur vers le format attendu
    par `generate_zone_recommendations()`.

    Le collecteur stocke les données avec des clés comme "risques_commune"
    et des sous-clés "data". Le générateur attend un format plat avec
    des clés comme "risquesNaturels", "catnat", "argiles_rga", etc.
    """
    if not georisques:
        return {}

    def _safe_data_list(key: str) -> list:
        """Extrait une liste depuis soit data.key soit key.data"""
        val = georisques.get(key) or {}
        if isinstance(val, list):
            return val
        if isinstance(val, dict):
            data = val.get("data")
            return data if isinstance(data, list) else []
        return []

    # Risques naturels (format risques_commune)
    risques_commune = georisques.get("risques_commune") or {}
    risques_data = risques_commune.get("data") if isinstance(risques_commune, dict) else []
    risques_naturels = {}
    if isinstance(risques_data, list):
        for entry in risques_data:
            for detail in entry.get("risques_detail") or []:
                libelle = (detail.get("libelle_risque_long") or "").lower()
                if "inondation" in libelle:
                    risques_naturels["inondation"] = {"present": True}
                if "retrait" in libelle or "argile" in libelle:
                    risques_naturels["retraitGonflementArgile"] = {"present": True}
                if "feu" in libelle or "forêt" in libelle or "foret" in libelle:
                    risques_naturels["feuForet"] = {"present": True}
                if "mouvement" in libelle:
                    risques_naturels["mouvementTerrain"] = {"present": True}
                if "radon" in libelle:
                    risques_naturels["radon"] = {"present": True}
                if "séisme" in libelle or "seisme" in libelle or "sismique" in libelle:
                    risques_naturels["seisme"] = {"present": True}

    # CATNAT (arrêtés de catastrophe naturelle)
    catnat_raw = georisques.get("catnat") or {}
    catnat_data = catnat_raw.get("data") if isinstance(catnat_raw, dict) else catnat_raw
    if isinstance(catnat_data, list):
        catnat_data = [
            {"risque_naturel": e.get("libelle_risque_jo", "")}
            for e in catnat_data
        ]
    else:
        catnat_data = []

    # Sismique : zone depuis le zonage
    zonage_list = _safe_data_list("zonage_sismique")
    zonage_result = [{"zone": z.get("zone_sismicite", "1")} for z in zonage_list] if zonage_list else []

    return {
        "risquesNaturels": risques_naturels,
        "argiles_rga": _safe_data_list("argiles_rga"),
        "zonage_sismique": zonage_result,
        "radon": _safe_data_list("radon"),
        "cavites": _safe_data_list("cavites"),
        "mouvements_terrain": _safe_data_list("mouvements_de_terrain"),
        "catnat": catnat_data,
        "icpe": [],
        "sites_sols_pollues": {},
    }


def _normaliser_climat(climat: dict[str, Any] | None) -> dict[str, Any]:
    """Normalise les données climat Open-Meteo vers le format attendu
    par `generate_zone_recommendations()` (clés camelCase anglaises).
    """
    if not climat:
        return {}
    ref = climat.get("reference_2015_2024") or {}
    return {
        "heatwaveDaysPerYear": ref.get("jours_chaleur_extreme_par_an", 0) or 0,
        "annualPrecipitation": ref.get("precipitation_annuelle_moyenne_mm", 0) or 0,
        "freezeDaysPerYear": 0,  # non disponible dans Open-Meteo actuel
        "stormFrequency": 0,      # non disponible dans Open-Meteo actuel
        "soilMoisture": 0.3,      # valeur par défaut conservative
        "temperatureMaxC": ref.get("temperature_max_moyenne_c", 15) or 15,
    }


def _enrichir_zones_avec_recommandations(
    zones: dict[str, Any],
    building_data: dict[str, Any],
    formulaire: dict[str, Any] | None,
) -> dict[str, Any]:
    """Enrichit les zones de scoring avec les recommandations du générateur existant.

    Utilise `generate_zone_recommendations()` (backend/api/recommandations_generator.py)
    pour produire des recommandations détaillées (coûts, normes, aides financières).
    Normalise les données au préalable pour correspondre au format attendu.
    """
    if not _HAS_RECO_GENERATOR or _generate_zone_recommendations is None:
        logger.warning(
            "digital_twin -- générateur recommandations INDISPONIBLE "
            "(zones retournées sans recommandations)"
        )
        return zones

    try:
        # Normaliser les données au format attendu par le générateur
        georisques_raw = building_data.get("georisques") or {}
        georisques_normalise = _normaliser_georisques(georisques_raw)
        climat_normalise = _normaliser_climat(building_data.get("climat_open_meteo") or {})

        api_data = {
            "georisques": georisques_normalise,
            "open_meteo": climat_normalise,
            "climate": climat_normalise,
            "bdnb": building_data.get("bdnb") or {},
            "building": building_data.get("bdnb") or {},
            "altitude": {"altitude": building_data.get("altitude_m") or 50},
            "altitude_m": building_data.get("altitude_m") or 50,
        }

        logger.info(
            "digital_twin -- appel generate_zone_recommendations "
            "(georisques=%s, climat=%s, form=%s)",
            "OK" if georisques_normalise else "vide",
            "OK" if climat_normalise else "vide",
            "OK" if formulaire else "None",
        )

        recos_result = _generate_zone_recommendations(
            api_data=api_data,
            form_data=formulaire or {},
        )

        recos_zones = recos_result.get("zones", {})
        total_recos_gen = sum(
            len(z.get("recommandations", []))
            for z in recos_zones.values()
            if isinstance(z, dict)
        )
        logger.info(
            "digital_twin -- generate_zone_recommendations OK : "
            "%d zone(s), %d recommandation(s) générée(s)",
            len(recos_zones),
            total_recos_gen,
        )

        if not recos_zones:
            logger.info("  -> aucune recommandation générée par le générateur")
            return zones

        # Fusionner les recommandations dans les zones du scoring
        nb_enrichies = 0
        for zone_name in zones:
            if zone_name in recos_zones:
                reco_zone = recos_zones[zone_name]
                recos_list = reco_zone.get("recommandations", [])
                if recos_list:
                    zones[zone_name]["recommandations"] = recos_list
                    zones[zone_name]["test_vulnerabilite"] = reco_zone.get("test_vulnerabilite", {})
                    nb_enrichies += 1
                    logger.debug(
                        "  -> zone '%s' enrichie avec %d recommandation(s)",
                        zone_name,
                        len(recos_list),
                    )

        logger.info(
            "digital_twin -- %d zone(s) enrichies avec recommandations "
            "(sur %d zone(s) au total)",
            nb_enrichies,
            len(zones),
        )
    except Exception as e:
        logger.exception(
            "digital_twin -- ÉCHEC génération recommandations: %s",
            e,
        )

    return zones


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

    # Enrichir les zones avec les recommandations du générateur existant
    zones_enrichies = _enrichir_zones_avec_recommandations(
        zones=risk_result["zones"],
        building_data=building_data,
        formulaire=formulaire,
    )

    # Projection 2050 : reprise directe du scoring (risk_model)
    # L'aggravation spécifique à l'analyse crédit est gérée dans bank_agent.py
    projection_2050 = risk_result.get("projection_2050", {})

    contract = {
        "adresse": adresse_info.get("label", ""),
        "bien": {
            "type": _bien_type(bdnb),
            "annee_construction": annee_construction,
            "coordonnees": {"lat": adresse_info.get("lat"), "lon": adresse_info.get("lon")},
        },
        "geometry": geometry,
        "score_global": risk_result["score_global"],
        "zones": zones_enrichies,
        "projection_2050": projection_2050,
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
