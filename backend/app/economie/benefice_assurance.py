"""
F-B2 — Bénéfice assurantiel annuel (niveau B).

Formule (doc §3.3 / F-B2) :
    B_assu = p × (c_sin − f) + Δs
    p    = probabilité annuelle de sinistre = fréquence réelle des arrêtés
           CATNAT de la commune (collector_agent -> georisques.catnat.data)
    c_sin = coût moyen d'un sinistre (RGA : 16 500 € Cour des Comptes /
           21 000 € CCR ; inondation : 10 900–17 800 € BRGM/CCR)
    f    = franchise légale (380 € aléas courants / 1 520 € RGA — D.125-5)
    Δs   = modulation de surprime liée à la prévention = 0 aujourd'hui
           (cadre Lavarde/PPL 2024) -> jamais chiffrée, juste signalée

Adaptation : seules les valeurs France (CCR / Cour des Comptes / BRGM) sont
utilisées, pas de coûts étrangers. La fenêtre de 30 ans pour convertir le
nombre d'arrêtés en probabilité annuelle est une HYPOTHÈSE du projet,
affichée comme telle.
"""

from __future__ import annotations

from typing import Any

from app.economie.schemas import CALCULE, FOURCHETTE, NULL, bloc, bloc_null, sommes_blocs
from app.economie.sources import source_refs

# Fenêtre d'observation (ans) pour convertir le nombre d'arrêtés CATNAT en
# probabilité annuelle. Hypothèse projet documentée (historique CatNat ~1995-2024).
_FENETRE_ANS = 30.0
_P_CAP = 1.0

# Chaque aléa : mots-clés de libellé CATNAT, coût moyen de sinistre (bornes),
# franchise légale, sources.
_ALEAS = {
    "retrait_gonflement_argiles": {
        "label": "Retrait-gonflement des argiles",
        "keywords": ("secheresse", "sécheresse"),
        "cout_min": 16_500.0,   # Cour des Comptes (ecologie.gouv.fr)
        "cout_max": 21_000.0,   # CCR / SDES 2023
        "franchise": 1_520.0,   # D.125-5 (RGA)
        "sources_cout": ("COURCOMPTES", "CCR2023"),
    },
    "inondation": {
        "label": "Inondation / coulées de boue",
        "keywords": ("inondation", "coulee", "coulée"),
        "cout_min": 10_900.0,   # indemnisation CatNat 1989-2002 (BRGM RP-56771-FR)
        "cout_max": 17_800.0,   # procédure exceptionnelle (BRGM RP-56771-FR)
        "franchise": 380.0,     # D.125-5 (aléas courants)
        "sources_cout": ("BRGM2009",),
    },
}


def _count_catnat(building_data: dict[str, Any], keywords: tuple[str, ...]) -> int:
    """Nombre d'arrêtés CATNAT de la commune dont le libellé contient l'un
    des mots-clés (même logique que risk_model._count_catnat)."""
    georisques = building_data.get("georisques") or {}
    catnat = georisques.get("catnat") or {}
    if isinstance(catnat, list):
        data = catnat
    elif isinstance(catnat, dict):
        data = catnat.get("data")
    else:
        data = None
    if not isinstance(data, list):
        return 0
    return sum(
        1
        for a in data
        if any(kw in str(a.get("libelle_risque_jo") or "").lower() for kw in keywords)
    )


def _benefice_alea(building_data: dict[str, Any], alea: str, config: dict[str, Any]) -> dict[str, Any]:
    nb = _count_catnat(building_data, config["keywords"])
    p = min(nb / _FENETRE_ANS, _P_CAP)

    if p <= 0:
        # Donnée réelle présente mais aucun arrêté pour cet aléa -> bénéfice
        # nul et calculé (p=0), pas un vide de données.
        return {
            "alea": alea,
            "label": config["label"],
            "nb_arretes": nb,
            "probabilite_annuelle": round(p, 4),
            "benefice": bloc(
                statut=CALCULE,
                valeur=0.0,
                min=0.0,
                max=0.0,
                sources=source_refs("CATNAT_GEO", *config["sources_cout"], "D1255"),
                hypotheses=[
                    "aucun arrêté CATNAT de cet aléa sur la commune -> p=0 -> "
                    "bénéfice assurantiel annuel nul"
                ],
                confidence=60,
            ),
            "statut": CALCULE,
        }

    b_min = p * (config["cout_min"] - config["franchise"])
    b_max = p * (config["cout_max"] - config["franchise"])
    return {
        "alea": alea,
        "label": config["label"],
        "nb_arretes": nb,
        "probabilite_annuelle": round(p, 4),
        "benefice": bloc(
            statut=FOURCHETTE,
            min=round(b_min, 2),
            max=round(b_max, 2),
            sources=source_refs("CATNAT_GEO", *config["sources_cout"], "D1255"),
            hypotheses=[
                f"probabilité annuelle = {nb} arrêté(s) / {_FENETRE_ANS:.0f} ans "
                "(fenêtre d'observation, hypothèse projet)",
                "coût moyen de sinistre borné par deux sources officielles "
                "(voir sources)",
            ],
            confidence=50,
        ),
        "statut": FOURCHETTE,
    }


def benefice_assurance(building_data: dict[str, Any]) -> dict[str, Any]:
    """Niveau B complet (F-B2).

    Retourne :
      {
        "par_alea": {...},
        "total": bloc,
        "modulation_surprime": {...cadre réglementaire à venir...},
      }
    """
    catnat_present = bool((building_data.get("georisques") or {}).get("catnat"))
    par_alea = {alea: _benefice_alea(building_data, alea, cfg) for alea, cfg in _ALEAS.items()}

    if not catnat_present:
        total = bloc_null(
            "aucune donnée CATNAT collectée pour cette commune → probabilité "
            "de sinistre inconnue → bénéfice assurantiel non calculé"
        )
    else:
        total = sommes_blocs([pa["benefice"] for pa in par_alea.values()])

    return {
        "par_alea": par_alea,
        "total": total,
        "modulation_surprime": {
            "statut": "cadre_reglementaire_a_venir",
            "valeur": 0.0,
            "sources": source_refs("ARRETE2023", "SENAT2024"),
            "raison": (
                "Δs (modulation de surprime selon la prévention) reste 0 tant que "
                "le cadre réglementaire (rapport Lavarde r23-603, PPL du 29/10/2024) "
                "n'est pas en vigueur — jamais chiffré."
            ),
        },
    }
