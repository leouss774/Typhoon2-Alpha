"""
digital_twin_agent — dernier maillon du graphe (cf. README racine).

Ne collecte rien, ne calcule aucun score : assemble la geometrie
(`geometry_builder`), les scores (`scoring_agent`) et l'adresse/bien
(`collector_agent`) dans le contrat JSON unique consomme par la scene
Three.js (voir README, section "Jumeau numerique 3D — contrat de sortie").
"""

from __future__ import annotations

from typing import Any

from app.core.logging import get_logger
from app.digital_twin.geometry_builder import build_geometry_from_bdnb

logger = get_logger(__name__)

# Valeurs de repli MVP pour les champs que ni la BDNB ni le formulaire ne
# couvrent aujourd'hui (cave/sous-sol/garage/jardin — cf. README next-steps
# §4 "Role de l'IA dans ce noeud" : a terme, un LLM complete ces champs a
# partir du contexte ; en attendant ce branchement, on applique un defaut
# documente plutot que de laisser une valeur nulle cassser le rendu 3D).
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
    logger.info("digital_twin_agent -- assemblage du contrat")

    adresse_info = building_data.get("adresse") or {}
    bdnb = building_data.get("bdnb")
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else {}
    batiment = batiment or {}

    geometry_report = build_geometry_from_bdnb(batiment, formulaire=formulaire, adresse=adresse_info)
    geometry = geometry_report["geometry"]
    if geometry_report["champs_manquants"]:
        logger.info(
            "  champs geometry non fournis par la BDNB/formulaire : %s (defauts MVP appliques)",
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
        # Metadonnees de fabrication, hors contrat frontend strict mais utiles
        # pour deboguer/auditer un diagnostic (ignorees par le rendu 3D).
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

    # DVF : enrichir la section marche si donnees disponibles
    dvf_data = building_data.get("dvf_local")
    if dvf_data:
        contract["marche"]["nb_transactions"] = len(dvf_data)
        # On garde un echantillon reduit pour le diagnostic promoteur
        contract["marche"]["dernieres_transactions"] = dvf_data[:5]

    # Copernicus : passe les donnees brutes en metadata (affichage conditionnel
    # dans l'UX, cf. _sources.climat_copernicus)
    if climat_copernicus:
        contract["_sources"]["climat_copernicus_raw"] = climat_copernicus

    logger.info(
        "  -> contrat pret : score_global=%d, %d zone(s), geometry=%.1fx%.1fm / %d etage(s), dvf=%s, copernicus=%s",
        contract["score_global"],
        len(contract["zones"]),
        geometry["largeur_m"],
        geometry["longueur_m"],
        geometry["floors_count"],
        contract["marche"]["dvf_disponible"],
        contract["_sources"]["climat_copernicus"],
    )
    return contract

    logger.info(
        "  -> contrat pret : score_global=%d, %d zone(s), geometry=%.1fx%.1fm / %d etage(s)",
        contract["score_global"],
        len(contract["zones"]),
        geometry["largeur_m"],
        geometry["longueur_m"],
        geometry["floors_count"],
    )
    return contract
