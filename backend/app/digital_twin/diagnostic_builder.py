"""
diagnostic_builder — dernier maillon du graphe (cf. README racine).

Ne collecte rien, ne calcule aucun score : assemble la géométrie
(`geometry_builder`), les scores (`scoring_agent`), les interprétations
(`interpretation_agent`) et les données du bien (`collector_agent`) dans
le diagnostic JSON unique consommé par la scène Three.js du frontend
(voir README, section "Jumeau numérique 3D — format de sortie").
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.digital_twin.geometry_builder import build_geometry_from_bdnb

logger = get_logger(__name__)

# Valeurs de repli MVP pour les champs que ni la BDNB ni le formulaire ne
# couvrent aujourd'hui (cave/sous-sol/garage/jardin — cf. README next-steps
# §4 "Rôle de l'IA dans ce noeud" : à terme, un LLM complète ces champs à
# partir du contexte ; en attendant ce branchement, on applique un défaut
# documenté plutôt que de laisser une valeur nulle casser le rendu 3D).
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


def build_diagnostic(
    building_data: dict[str, Any],
    risk_result: dict[str, Any],
    formulaire: dict[str, Any] | None = None,
    interpretations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble le diagnostic final de vulnérabilité climatique.

    Combine les données collectées (building_data), les scores de risque
    (risk_result), les interprétations LLM (interpretations) et la géométrie
    du bâtiment dans un dictionnaire unique transmis au frontend.

    Returns
    -------
    dict
        Le diagnostic complet avec adresse, bien, geometry, score_global,
        zones (enrichies des conclusions interprétées), projection_2050,
        climat, marché (DVF), et métadonnées de construction.
    """
    logger.info("diagnostic_builder -- assemblage du diagnostic")

    adresse_info = building_data.get("adresse") or {}
    bdnb = building_data.get("bdnb")
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else {}
    batiment = batiment or {}

    geometry_report = build_geometry_from_bdnb(batiment, formulaire=formulaire, adresse=adresse_info)
    geometry = geometry_report["geometry"]
    if geometry_report["champs_manquants"]:
        logger.info(
            "  champs geometry non fournis par la BDNB/formulaire : %s (défauts MVP appliqués)",
            ", ".join(geometry_report["champs_manquants"]),
        )
    annee_construction = batiment.get("annee_construction")
    _apply_mvp_defaults(geometry, annee_construction)

    climat_open_meteo = building_data.get("climat_open_meteo") or {}
    projection = climat_open_meteo.get("projection_2041_2050") or {}
    reference = climat_open_meteo.get("reference_2015_2024") or {}

    # Source text for climate data
    source_parts = ["Open-Meteo Climate API — moyenne des modèles climatiques, projection 2041-2050"]
    if reference.get("temperature_max_moyenne_c") is not None:
        source_parts.append(f"référence 2015-2024 : {reference['temperature_max_moyenne_c']}°C")

    # Copernicus enrichment flag
    climat_copernicus = building_data.get("climat_copernicus")
    if climat_copernicus:
        source_parts.append("+ données Copernicus CDS disponibles (climat_copernicus)")

    # Enrichir chaque zone avec la conclusion interprétée (si disponible)
    interpretations = interpretations or {}
    zones_enriched = {}
    for zone_name, zone_data in risk_result["zones"].items():
        zone_copy = dict(zone_data)
        interp = interpretations.get(zone_name)
        if interp:
            # La conclusion enrichie remplace la justification technique
            # dans l'affichage principal (le front n'affiche pas "interprétation")
            zone_copy["conclusion"] = interp.get("conclusion", "")
            zone_copy["facteurs_aggravants"] = interp.get("facteurs_aggravants", [])
            zone_copy["facteurs_attenuants"] = interp.get("facteurs_attenuants", [])
            zone_copy["vulnerabilite"] = interp.get("vulnerabilite", "moderee")
        else:
            zone_copy["conclusion"] = ""
            zone_copy["facteurs_aggravants"] = []
            zone_copy["facteurs_attenuants"] = []
            zone_copy["vulnerabilite"] = zone_data.get("niveau", "modere")
        zones_enriched[zone_name] = zone_copy

    diagnostic = {
        "adresse": adresse_info.get("label", ""),
        "bien": {
            "type": _bien_type(bdnb),
            "annee_construction": annee_construction,
            "coordonnees": {"lat": adresse_info.get("lat"), "lon": adresse_info.get("lon")},
        },
        "geometry": geometry,
        "score_global": risk_result["score_global"],
        "zones": zones_enriched,
        "projection_2050": risk_result["projection_2050"],
        "climat": {
            "2050": {
                "temperature_max_projetee_c": projection.get("temperature_max_absolue_c") if projection.get("temperature_max_absolue_c") is not None else projection.get("temperature_max_moyenne_c"),
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
            "source": " — ".join(source_parts),
        },
        "marche": {
            "dvf_disponible": bool(building_data.get("dvf_local")),
        },
        # Métadonnées de fabrication, hors diagnostic frontend strict mais utiles
        # pour déboguer/auditer un diagnostic (ignorées par le rendu 3D).
        "_geometry_build_report": {
            "champs_ok": geometry_report["champs_ok"],
            "champs_manquants_bdnb": geometry_report["champs_manquants"],
        },
        "_sources": {
            "climat_open_meteo": bool(climat_open_meteo),
            "climat_copernicus": bool(climat_copernicus),
            "dvf_local": bool(building_data.get("dvf_local")),
        },
        "_erreurs_collecte": building_data.get("erreurs", []),
    }

    # DVF : enrichir la section marché si données disponibles
    dvf_data = building_data.get("dvf_local")
    if dvf_data:
        diagnostic["marche"]["nb_transactions"] = len(dvf_data)
        diagnostic["marche"]["dernieres_transactions"] = dvf_data[:5]

    # Copernicus : passe les données brutes en metadata (affichage conditionnel)
    if climat_copernicus:
        diagnostic["_sources"]["climat_copernicus_raw"] = climat_copernicus

    logger.info(
        "  -> diagnostic prêt : score_global=%d, %d zone(s), geometry=%.1fx%.1fm / %d étage(s), dvf=%s, copernicus=%s",
        diagnostic["score_global"],
        len(diagnostic["zones"]),
        geometry["largeur_m"],
        geometry["longueur_m"],
        geometry["floors_count"],
        diagnostic["marche"]["dvf_disponible"],
        diagnostic["_sources"]["climat_copernicus"],
    )
    return diagnostic
