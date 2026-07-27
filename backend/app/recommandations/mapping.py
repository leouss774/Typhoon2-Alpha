"""
Alignement du vocabulaire entre scoring_agent (app/scoring/risk_model.py) et
le referentiel documentaire du RAG recommandations — cf.
recommendation_travaux/PROMPT_INTEGRATION_ouss.md, section 4
"Aligner les noms de champs (contrat JSON exact attendu)".

Probleme concret : risk_model.py ne calcule pas un "alea" au sens du
referentiel (retrait_gonflement_argiles, inondation, tempete, canicule...)
par zone — il combine plusieurs sous-scores (argile, sismique, precipitations,
canicule...) et n'expose qu'un `alea_principal` en francais libre, pense pour
l'affichage humain (ex: "Infiltration (exposition nord)"), pas comme
identifiant machine.

ZONE_RISQUES fixe donc, zone par zone, la liste de risques normalises (meme
vocabulaire que data/referentiel.json : inondation, ruissellement, canicule,
tempete, feu_vegetation, secheresse, retrait_gonflement_argiles) a envoyer a
l'agent RAG. C'est une heuristique documentee (pas une mesure) qui reprend la
logique deja utilisee dans risk_model.py pour construire chaque zone :
  - fondations       : domine par le risque argile (cf. _argile_subscore)
  - murs_*           : domine par precipitations/sismique/canicule, avec un
                        risque distinct par orientation pour varier les fiches
                        remontees (nord = ruissellement, sud = canicule,
                        est/ouest = tempete, cf. _EXPOSITION_MURS_DELTA)
  - toiture          : canicule + tempete (cf. _compute_zones_for_period)
  - sous_sol         : inondation + ruissellement (cf. _inondation_subscore)

A ajuster si le referentiel s'enrichit (ex: ajout de fiches
"retrait_gonflement_argiles" hors fondations, ou de "grele"/"submersion").
"""

from __future__ import annotations

from typing import Any

ZONE_RISQUES: dict[str, list[str]] = {
    "fondations": ["retrait_gonflement_argiles"],
    "murs_nord": ["ruissellement"],
    "murs_sud": ["canicule"],
    "murs_est": ["tempete"],
    "murs_ouest": ["tempete"],
    "toiture": ["canicule", "tempete"],
    "sous_sol": ["inondation", "ruissellement"],
}


def build_house_payload(building_data: dict[str, Any], risk_result: dict[str, Any]) -> dict[str, Any]:
    """Construit le JSON "maison" attendu par l'agent RAG (cf. maison_exemple.json
    dans recommendation_travaux/), a partir de building_data (collector_agent)
    et risk_result (scoring_agent) — sans transformation manuelle cote agent RAG.
    """
    adresse_info = (building_data or {}).get("adresse") or {}
    bdnb = (building_data or {}).get("bdnb") or {}
    batiment = bdnb.get("batiment") if isinstance(bdnb, dict) else None
    batiment = batiment or {}

    zones_in = risk_result.get("zones") or {}
    zones_payload = []
    for zone_name in zones_in:
        risques = ZONE_RISQUES.get(zone_name)
        if not risques:
            continue
        zones_payload.append({"zone": zone_name, "risques": risques})

    return {
        "adresse": adresse_info.get("label", ""),
        "bien": {
            "type": "maison individuelle",
            "annee_construction": batiment.get("annee_construction"),
            "coordonnees": {"lat": adresse_info.get("lat"), "lon": adresse_info.get("lon")},
        },
        "zones": zones_payload,
    }
