"""
Contrat de sortie du volet économique — §6 du doc STRATEGIE_RETOUR_INVESTISSEMENT.md.

Règles d'affichage :
1. Chaque bloc économique renvoie { valeur, min, max, statut, sources, hypotheses, confidence }.
2. Trois statuts seulement : `calcule` (entrées réelles + formule référencée),
   `fourchette` (bornes d'une source publiée + sensibilité), `null` (aucun
   input disponible -> aucun chiffre affiché).
3. `confidence` est indépendant du score de risque (même philosophie que
   risk_model._compute_confidence).
"""

from __future__ import annotations

from typing import Any

CALCULE = "calcule"
FOURCHETTE = "fourchette"
NULL = "null"


def bloc(
    *,
    statut: str,
    valeur: float | int | None = None,
    min: float | int | None = None,
    max: float | int | None = None,
    sources: list[dict[str, str]] | None = None,
    hypotheses: list[str] | None = None,
    confidence: float | int | None = None,
    raison: str | None = None,
) -> dict[str, Any]:
    """Construit un bloc standard du contrat économique.

    `statut` doit être un des trois statuts du projet. `sources` est une
    liste de {"id", "reference"} produite par `app.economie.sources.source_refs`.
    """
    if statut not in (CALCULE, FOURCHETTE, NULL):
        raise ValueError(f"Statut economique inconnu : {statut!r}")
    if statut != NULL and not sources:
        # §6.2 : un montant n'est jamais affiché sans sa liste de sources.
        raise ValueError("Un bloc non-null doit porter au moins une source.")
    return {
        "statut": statut,
        "valeur": valeur,
        "min": min,
        "max": max,
        "sources": sources or [],
        "hypotheses": hypotheses or [],
        "confidence": confidence,
        "raison": raison,
    }


def bloc_null(raison: str) -> dict[str, Any]:
    """Bloc sans chiffre : statut `null` + la raison pour laquelle aucun
    montant n'est produit (conforme §6.3 : pas de chiffre -> pas d'arnaque)."""
    return {
        "statut": NULL,
        "valeur": None,
        "min": None,
        "max": None,
        "sources": [],
        "hypotheses": [],
        "confidence": None,
        "raison": raison,
    }


def sommes_blocs(blocs: list[dict[str, Any]]) -> dict[str, Any]:
    """Additionne des blocs en préservant les statuts.

    - Si tous les blocs sont `null` -> `null` (raison jointe).
    - Sinon : bornes = somme des bornes disponibles, statut `calcule` si
      toutes les entrées sont des points fixes, sinon `fourchette`.
    """
    actifs = [b for b in blocs if b.get("statut") != NULL]
    if not actifs:
        raisons = [b.get("raison") for b in blocs if b.get("raison")]
        return bloc_null(" ; ".join(raisons) or "aucune composante disponible")

    calcule = all(b.get("statut") == CALCULE for b in actifs)
    v_min = sum(b.get("min") or b.get("valeur") or 0.0 for b in actifs)
    v_max = sum(b.get("max") or b.get("valeur") or 0.0 for b in actifs)
    sources = [
        s
        for b in actifs
        for s in b.get("sources", [])
    ]
    hypotheses = [
        h
        for b in actifs
        for h in b.get("hypotheses", [])
    ]
    confidences = [b.get("confidence") for b in actifs if b.get("confidence") is not None]
    confidence = round(sum(confidences) / len(confidences)) if confidences else None

    if calcule and v_min == v_max:
        return bloc(
            statut=CALCULE,
            valeur=round(v_min, 2),
            min=round(v_min, 2),
            max=round(v_max, 2),
            sources=sources,
            hypotheses=hypotheses,
            confidence=confidence,
        )
    return bloc(
        statut=FOURCHETTE,
        min=round(v_min, 2),
        max=round(v_max, 2),
        sources=sources,
        hypotheses=hypotheses,
        confidence=confidence,
    )


def calculer_confiance(disponibles: list[bool], hypotheses: list[bool], qualite: float = 0.85) -> dict[str, Any]:
    """Score de confiance (0-100) du bloc économique, indépendant du risque.

    - Disponibilité des entrées (poids 0.60) : part de blocs non-null.
    - Hypothèses de modèle (poids 0.30) : moins d'hypothèses -> meilleur.
    - Qualité intrinsèque des sources (poids 0.10).
    """
    if not disponibles:
        return {"score": 0, "niveau": "indetermine", "composantes": {}}

    dispo = sum(1 for d in disponibles if d) / len(disponibles)
    hyp = 1.0 - (sum(1 for h in hypotheses if h) / len(hypotheses)) if hypotheses else 1.0
    score = dispo * 60.0 + hyp * 30.0 + qualite * 10.0

    if score >= 80:
        niveau = "elevee"
    elif score >= 60:
        niveau = "bonne"
    elif score >= 40:
        niveau = "moyenne"
    else:
        niveau = "faible"

    return {
        "score": round(score),
        "niveau": niveau,
        "composantes": {
            "disponibilite_entrees": round(dispo, 3),
            "absence_hypotheses": round(hyp, 3),
            "qualite_sources": round(qualite, 3),
        },
    }
