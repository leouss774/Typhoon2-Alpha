"""Moteur de calcul du score global déterministe.

Combine les scores de chaque aléa selon des pondérations
pour produire un score global de risque (0-100).
"""

from __future__ import annotations

from backend.services.scoring.weights import POIDS_ALEAS, get_niveau_risque


def compute_all_scores(client_form: dict, raw_data: dict) -> dict:
    """Calcule tous les scores déterministes pour un bien.

    Args:
        client_form: Données du formulaire client.
        raw_data: Données brutes (DRIAS, zonages, etc.).

    Returns:
        Dict avec score_global et scores_par_alea.
    """
    scores = {}

    scores["rga"] = _score_rga(client_form, raw_data)
    scores["inondation"] = _score_inondation(client_form, raw_data)
    scores["tempete"] = _score_tempete(client_form, raw_data)
    scores["feu_foret"] = _score_feu_foret(client_form, raw_data)
    scores["submersion"] = _score_submersion(client_form, raw_data)

    # Score global = moyenne pondérée
    score_global = sum(
        scores[alea] * POIDS_ALEAS.get(alea, 1.0)
        for alea in scores
    ) / sum(POIDS_ALEAS.get(alea, 1.0) for alea in scores)

    return {
        "score_global": round(score_global, 1),
        "scores_par_alea": {k: round(v, 1) for k, v in scores.items()},
    }


def _score_rga(client_form: dict, raw_data: dict) -> float:
    """Calcule le score de risque RGA (retrait-gonflement des argiles)."""
    # Facteurs : zonage argile, type sol, présence sous-sol, âge construction
    exposition = raw_data.get("exposition_argile", 0.5)  # 0-1
    sous_sol_penalty = 15 if client_form.get("sous_sol") else 0
    age_penalty = max(0, (2025 - client_form.get("annee_construction", 2000)) / 100 * 10)
    return min(100, exposition * 70 + sous_sol_penalty + age_penalty)


def _score_inondation(client_form: dict, raw_data: dict) -> float:
    """Calcule le score de risque inondation."""
    # Facteurs : zonage PPRI, proximité cours d'eau, altitude, sous-sol
    zone_ppri = raw_data.get("zone_ppri", "non")  # non | faible | moyen | fort
    ppri_map = {"non": 0, "faible": 20, "moyen": 50, "fort": 85}
    sous_sol_penalty = 20 if client_form.get("sous_sol") else 0
    return min(100, ppri_map.get(zone_ppri, 0) + sous_sol_penalty)


def _score_tempete(client_form: dict, raw_data: dict) -> float:
    """Calcule le score de risque tempête."""
    # Facteurs : zone vent, matériau toiture, exposition, altitude
    zone_vent = raw_data.get("zone_vent", 1)  # 1-4
    toiture_fragile = 1.3 if client_form.get("materiau_principal") == "bois" else 1.0
    return min(100, zone_vent * 20 * toiture_fragile)


def _score_feu_foret(client_form: dict, raw_data: dict) -> float:
    """Calcule le score de risque feu de forêt."""
    # Facteurs : proximité forêt, matériau, zone réglementaire
    proximite_foret = raw_data.get("proximite_foret_m", 5000)
    if proximite_foret > 2000:
        base = 5
    elif proximite_foret > 500:
        base = 30
    elif proximite_foret > 100:
        base = 60
    else:
        base = 85

    bois_penalty = 15 if client_form.get("materiau_principal") == "bois" else 0
    return min(100, base + bois_penalty)


def _score_submersion(client_form: dict, raw_data: dict) -> float:
    """Calcule le score de risque submersion marine."""
    # Facteurs : altitude, proximité côte, zone réglementaire
    altitude = raw_data.get("altitude_m", 50)
    distance_cote = raw_data.get("distance_cote_km", 100)

    if distance_cote > 20 or altitude > 20:
        return 5
    if altitude < 5 and distance_cote < 2:
        return 80
    if altitude < 10 or distance_cote < 5:
        return 40
    return 15


def compute_global_score(scores_par_alea: dict[str, float]) -> float:
    """Calcule le score global à partir des scores par aléa."""
    if not scores_par_alea:
        return 0.0

    total = sum(
        scores_par_alea[alea] * POIDS_ALEAS.get(alea, 1.0)
        for alea in scores_par_alea
    )
    poids_total = sum(POIDS_ALEAS.get(alea, 1.0) for alea in scores_par_alea)

    return round(total / poids_total, 1) if poids_total > 0 else 0.0
