"""
digital_twin_agent — dernier maillon du graphe (cf. README racine).

Ne collecte rien, ne calcule aucun score : assemble la geometrie
(`geometry_builder`), les scores numeriques (`risk_scoring_agent`),
les recommandations sourcees (`rag_agent`, optionnelles) et l'adresse/bien
(`collector_agent`) dans le contrat JSON unique consomme par la scene
Three.js (voir README, section "Jumeau numerique 3D — contrat de sortie").

Pont entre 2 vocabulaires de zones differents :
  - risk_scoring_agent (donc ce contrat / le rendu 3D) utilise 7 zones
    directionnelles : fondations, murs_nord/sud/est/ouest, toiture, sous_sol.
  - rag_agent (donc l'agent recommandations de la collegue) utilise 5 zones
    "metier" : fondations, toiture, facade, menuiseries, sous_sol - sans
    granularite directionnelle (aucune donnee Georisques/BDNB ne distingue
    les 4 facades). `_RAG_ZONE_VERS_ZONES_3D` fait ce pont : une recommandation
    "facade" ou "menuiseries" s'applique aux 4 zones murs_* du rendu 3D.
"""

from __future__ import annotations

import json
from typing import Any

from app.core.logging import get_logger
from app.digital_twin.geometry_builder import build_geometry_from_bdnb

logger = get_logger(__name__)

_RAG_ZONE_VERS_ZONES_3D: dict[str, list[str]] = {
    "fondations": ["fondations"],
    "sous_sol": ["sous_sol"],
    "toiture": ["toiture"],
    "facade": ["murs_nord", "murs_sud", "murs_est", "murs_ouest"],
    "menuiseries": ["murs_nord", "murs_sud", "murs_est", "murs_ouest"],
}


def _format_cout_estime(cout_estime: Any) -> str:
    if not cout_estime:
        return "coût non chiffré"
    if isinstance(cout_estime, str):
        return cout_estime
    if isinstance(cout_estime, dict):
        for cle in ("montant", "valeur", "estimation", "min_max", "fourchette"):
            if cout_estime.get(cle):
                return str(cout_estime[cle])
        return json.dumps(cout_estime, ensure_ascii=False)
    return str(cout_estime)


def _recommendations_to_front_format(recommendations: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    """rag_agent (5 zones qualitatives) -> {zone_3d: [items au format front]}.

    Chaque recommandation RAG (mesure/type/cout_estime/aide/sources) est
    reformatee au format attendu par `frontend/jumeau_numerique/index.html`
    (travaux/cout_estime/gain_resilience) ; `gain_resilience` reste `None`
    (rag_agent ne le calcule pas), le front doit deja gerer son absence.
    """
    by_zone_3d: dict[str, list[dict[str, Any]]] = {}
    if not recommendations:
        return by_zone_3d

    for rag_zone in recommendations.get("zones", []):
        cibles = _RAG_ZONE_VERS_ZONES_3D.get(rag_zone.get("zone"), [])
        for reco in rag_zone.get("recommandations", []):
            item = {
                "travaux": reco.get("mesure", "Recommandation"),
                "cout_estime": _format_cout_estime(reco.get("cout_estime")),
                "gain_resilience": None,
                "type": reco.get("type"),
                "sources": reco.get("sources", []),
            }
            for zone_3d in cibles:
                by_zone_3d.setdefault(zone_3d, []).append(item)
    return by_zone_3d

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
    recommendations: dict[str, Any] | None = None,
    formulaire: dict[str, Any] | None = None,
) -> dict[str, Any]:
    logger.info("digital_twin_agent -- assemblage du contrat")

    recos_par_zone = _recommendations_to_front_format(recommendations)
    if recommendations is not None:
        nb_recos = sum(len(v) for v in recos_par_zone.values())
        logger.info("  rag_agent : %d recommandation(s) réparties sur %d zone(s) 3D", nb_recos, len(recos_par_zone))
    else:
        logger.info("  rag_agent : aucune recommandation reçue (noeud absent, échoué, ou clé Mistral non configurée)")

    adresse_info = building_data.get("adresse") or {}
    bdnb = building_data.get("bdnb")
    batiment = (bdnb or {}).get("batiment") if isinstance(bdnb, dict) else {}
    batiment = batiment or {}

    geometry_report = build_geometry_from_bdnb(batiment, formulaire=formulaire)
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

    # Injecte les recommandations RAG dans les 7 zones numeriques (2025 et
    # projection 2050 - rag_agent ne differencie pas par horizon temporel,
    # les memes recommandations s'appliquent aux deux jeux de zones).
    for zones_bloc in (risk_result.get("zones"), (risk_result.get("projection_2050") or {}).get("zones")):
        if not zones_bloc:
            continue
        for zone_name, items in recos_par_zone.items():
            if zone_name in zones_bloc:
                zones_bloc[zone_name].setdefault("recommandations", [])
                zones_bloc[zone_name]["recommandations"].extend(items)

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
        "climat_2050": {
            "temperature_max_projetee_c": projection.get("temperature_max_moyenne_c"),
            "source": (
                "Open-Meteo Climate API — moyenne des modèles climatiques, "
                "projection 2041-2050"
                + (f" (référence 2015-2024 : {reference['temperature_max_moyenne_c']}°C)" if reference.get("temperature_max_moyenne_c") is not None else "")
            ),
        },
        # Metadonnees de fabrication, hors contrat frontend strict mais utiles
        # pour deboguer/auditer un diagnostic (ignorees par le rendu 3D).
        "_geometry_build_report": {
            "champs_ok": geometry_report["champs_ok"],
            "champs_manquants_bdnb": geometry_report["champs_manquants"],
        },
        "_erreurs_collecte": building_data.get("erreurs", []),
    }

    logger.info(
        "  -> contrat pret : score_global=%d, %d zone(s), geometry=%.1fx%.1fm / %d etage(s)",
        contract["score_global"],
        len(contract["zones"]),
        geometry["largeur_m"],
        geometry["longueur_m"],
        geometry["floors_count"],
    )
    return contract
