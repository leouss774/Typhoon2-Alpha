"""
risk_mapper.py
--------------
Le risk engine (orchestrateur) sort des scores PAR PÉRIL
(infiltration, thermique, incendie_électrique, aléas_naturels), alors que le
jumeau numérique 3D attend des scores PAR ZONE PHYSIQUE de la maison
(fondations, murs_nord/sud/est/ouest, toiture, sous_sol).

Ce module est l'adaptateur entre les deux. Le mapping péril -> zone est une
RÈGLE MÉTIER par défaut (pondérations ci-dessous), documentée et isolée ici
pour être ajustée facilement sans toucher au reste du pipeline. Dès que des
données directionnelles réelles seront disponibles (exposition solaire,
vents dominants, orientation du bâtiment via geometry_service), la
pondération des murs pourra être affinée avec `orientation_deg`.

Entrée : le bloc "step7" de merged_input.json (score déterministe + périls).
Sortie : un dict prêt à être validé par ZonesDataset (jumeau_schemas.py).
"""

from __future__ import annotations

from backend.models.jumeau_schemas import niveau_from_score

# Pondérations par défaut péril -> zone. Chaque zone combine 1 à 2 périls.
_WEIGHTS = {
    "fondations": {"aléas_naturels": 0.65, "infiltration": 0.35},
    "sous_sol": {"infiltration": 0.8, "aléas_naturels": 0.2},
    "toiture": {"thermique": 0.7, "infiltration": 0.3},
    "murs_nord": {"thermique": 0.35, "incendie_électrique": 0.25, "infiltration": 0.40},
    "murs_sud": {"thermique": 0.55, "incendie_électrique": 0.25, "infiltration": 0.20},
    "murs_est": {"thermique": 0.45, "incendie_électrique": 0.30, "infiltration": 0.25},
    "murs_ouest": {"thermique": 0.50, "incendie_électrique": 0.25, "infiltration": 0.25},
}

_DEFAULT_ALEA_LABEL = {
    "infiltration": "Infiltration / humidité",
    "thermique": "Stress thermique",
    "incendie_électrique": "Risque électrique",
    "aléas_naturels": "Aléas naturels (sol, sismique, RGA)",
}


def _clamp_score(value: float) -> int:
    return max(0, min(100, round(value)))


def _top_rule_for_perils(step7: dict, perils: list[str]) -> dict | None:
    """Retourne la règle déclenchée (triggered_rules) la plus prioritaire parmi les périls donnés."""
    best = None
    for peril_key in perils:
        peril_block = step7.get("score", {}).get("perils", {}).get(peril_key, {})
        for rule in peril_block.get("triggered_rules", []):
            if best is None or rule.get("priority", 0) > best.get("priority", 0):
                best = rule
    return best


def _zone_score(step7: dict, weights: dict[str, float]) -> float:
    perils = step7.get("score", {}).get("perils", {})
    total = 0.0
    total_weight = 0.0
    for peril_key, w in weights.items():
        peril_score = perils.get(peril_key, {}).get("score")
        if peril_score is None:
            continue
        total += peril_score * w
        total_weight += w
    if total_weight == 0:
        return 0.0
    return total / total_weight  # renormalise si un péril est absent des données


def map_step7_to_zones(step7: dict) -> dict:
    """
    Transforme step7 (issu du risk engine, cf. merged_input.json) en dict de
    zones conforme au contrat attendu par jumeau_schemas.ZonesDataset.
    Les `recommandations` sont laissées vides ici : elles sont fournies par
    l'Agent Recommandation (RAG, déjà développé par ailleurs) et fusionnées
    séparément via `merge_recommandations()` ci-dessous.
    """
    zones: dict[str, dict] = {}
    for zone_name, weights in _WEIGHTS.items():
        score = _clamp_score(_zone_score(step7, weights))
        dominant_peril = max(weights, key=weights.get)
        top_rule = _top_rule_for_perils(step7, list(weights.keys()))

        alea_principal = (
            top_rule["peril"].replace("_", " ").capitalize() + " — " + _short_label(top_rule)
            if top_rule else _DEFAULT_ALEA_LABEL.get(dominant_peril, dominant_peril)
        )
        justification = top_rule["justification"] if top_rule else (
            f"Score dérivé des périls {', '.join(weights.keys())} "
            f"(pondération {zone_name}), aucune règle spécifique déclenchée."
        )

        zones[zone_name] = {
            "risque": score,
            "niveau": niveau_from_score(score),
            "alea_principal": alea_principal,
            "justification": justification,
            "recommandations": [],
        }
    return zones


def _short_label(rule: dict) -> str:
    """Libellé court dérivé de l'id de règle, pour compléter alea_principal."""
    return rule["rule_id"].replace("_", " ").lower()


def build_score_global(step7: dict) -> int:
    return _clamp_score(step7.get("score", {}).get("global", 0))


def merge_recommandations(zones: dict, recommandations_par_zone: dict[str, list[dict]] | None) -> dict:
    """
    Fusionne les recommandations produites par l'Agent Recommandation (RAG)
    dans le dict de zones déjà construit par map_step7_to_zones().
    `recommandations_par_zone` : {"fondations": [{"travaux": ..., "cout_estime": ..., "gain_resilience": ...}], ...}
    Si absent (agent pas encore branché), les zones gardent une liste vide --
    le jumeau reste affichable, seul le panneau "recommandations" sera vide.
    """
    if not recommandations_par_zone:
        return zones
    for zone_name, recos in recommandations_par_zone.items():
        if zone_name in zones:
            zones[zone_name]["recommandations"] = recos
    return zones


if __name__ == "__main__":
    import json
    import pathlib

    sample_path = pathlib.Path(__file__).resolve().parents[2] / "sample_data" / "merged_input.json"
    if sample_path.exists():
        merged = json.loads(sample_path.read_text())
        step7 = merged["step7"]
        zones = map_step7_to_zones(step7)
        print(json.dumps({"score_global": build_score_global(step7), "zones": zones}, ensure_ascii=False, indent=2))
    else:
        print(f"Fichier d'exemple introuvable : {sample_path} (voir sample_data/merged_input.json)")
