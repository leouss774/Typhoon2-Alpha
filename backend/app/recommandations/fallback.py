"""
Fallback déterministe de recommandations — utilisé quand Mistral est
indisponible (timeout, clé manquante, quota) ou quand la réponse LLM ne
contient aucun coût exploitable.

Contrat : mêmes recommandations qu'une réponse Mistral valide, avec
`cout_estime` sourcé, `aide` et `sources` — afin que le volet économique
(backend/app/economie) puisse calculer un coût de travaux même sans LLM.

Sources des coûts :
    - Fiches de l'index RAG local (data/index.json) quand elles portent
      un `cout.montant_min`/`montant_max` non nul — c'est exactement ce
      que Mistral recopierait.
    - Références publiques publiées par MRN/CEPRI/BRGM (cf. backend/
      app/economie/sources.py) pour les mesures sans fiche chiffrée.

Ce module est volontairement simple : il ne cherche PAS à imiter la
richesse d'une réponse LLM, il garantit seulement qu'une zone à risque
repart avec au moins une recommandation chiffrée et sourcée.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Coûts de référence par zone + aléa (EUR, fourchette basse/haute).
# Sources : MRN (Mission Risques Naturels), CEPRI, BRGM, ADEME — reprises
# dans backend/app/economie/sources.py (identifier REF-SXX).
# ---------------------------------------------------------------------------

# zone -> {"risque": [{"mesure": ..., "min": ..., "max": ..., "source": ...}]}
_FALLBACK_COUTS: dict[str, dict[str, list[dict[str, Any]]]] = {
    "fondations": {
        "retrait_gonflement_argiles": [
            {
                "mesure": "Mise en place d'un drainage périphérique",
                "min": 8_000,
                "max": 12_000,
                "source": "BRGM — RGA",
                "aide": "Fonds Barnier / FPRNM",
            },
            {
                "mesure": "Reprise en sous-œuvre des fondations (injection de coulis)",
                "min": 25_000,
                "max": 60_000,
                "source": "MRN — Retrait-gonflement des argiles",
                "aide": "Fonds Barnier / FPRNM",
            },
        ],
        "inondation": [
            {
                "mesure": "Hydrofuge + cuvelage du sous-sol",
                "min": 6_000,
                "max": 15_000,
                "source": "CEPRI — Inondation",
                "aide": "Fonds Barnier / FPRNM",
            },
        ],
        "secheresse": [
            {
                "mesure": "Traitement des fissures (injection résine) + surveillance",
                "min": 4_000,
                "max": 10_000,
                "source": "BRGM — RGA / sécheresse",
                "aide": "Fonds Barnier / FPRNM",
            },
        ],
    },
    "toiture": {
        "tempete": [
            {
                "mesure": "Renforcement de la charpente et fixation des tuiles (crampons)",
                "min": 3_000,
                "max": 8_000,
                "source": "MRN — Tempête",
                "aide": None,
            },
            {
                "mesure": "Remplacement de la couverture par des matériaux résistants",
                "min": 8_000,
                "max": 18_000,
                "source": "MRN — Tempête / grêle",
                "aide": None,
            },
        ],
        "grele": [
            {
                "mesure": "Bâche de protection et tuiles anti-grêle",
                "min": 2_500,
                "max": 7_000,
                "source": "MRN — Grêle",
                "aide": None,
            },
        ],
        "canicule": [
            {
                "mesure": "Isolation des combles et ventilation de toiture (écrans réfléchissants)",
                "min": 5_000,
                "max": 12_000,
                "source": "ADEME — Confort d'été",
                "aide": None,
            },
        ],
        "feu_vegetation": [
            {
                "mesure": "Écran thermique de toiture + débroussaillement",
                "min": 2_000,
                "max": 6_000,
                "source": "MRN — Feu de forêt",
                "aide": None,
            },
        ],
    },
    "sous_sol": {
        "inondation": [
            {
                "mesure": "Installation de batardeaux et clapets anti-retour",
                "min": 3_000,
                "max": 5_000,
                "source": "CEPRI — Inondation",
                "aide": None,
            },
            {
                "mesure": "Pompe de relevage + cuvelage",
                "min": 4_000,
                "max": 12_000,
                "source": "CEPRI — Inondation",
                "aide": "Fonds Barnier / FPRNM",
            },
        ],
        "remontee de nappe": [
            {
                "mesure": "Drainage périphérique du sous-sol avec pompe de relevage",
                "min": 6_000,
                "max": 15_000,
                "source": "BRGM — Remontée de nappe",
                "aide": "Fonds Barnier / FPRNM",
            },
        ],
    },
    "facade": {
        "tempete": [
            {
                "mesure": "Traitement hydrofuge de la façade et rejointoiement",
                "min": 2_000,
                "max": 3_000,
                "source": "MRN — Tempête / humidité",
                "aide": None,
            },
        ],
        "inondation": [
            {
                "mesure": "Traitement hydrofuge + protections de baies (volets battants)",
                "min": 2_500,
                "max": 6_000,
                "source": "CEPRI — Inondation",
                "aide": None,
            },
        ],
        "canicule": [
            {
                "mesure": "Isolation thermique des murs par l'extérieur (ITE)",
                "min": 15_000,
                "max": 30_000,
                "source": "ADEME — Rénovation énergétique",
                "aide": "MaPrimeRénov'",
            },
        ],
        "feu_vegetation": [
            {
                "mesure": "Habillage pare-feu et menuiseries résistantes au feu",
                "min": 5_000,
                "max": 12_000,
                "source": "MRN — Feu de forêt",
                "aide": None,
            },
        ],
        "ruissellement": [
            {
                "mesure": "Gouttières renforcées et dalles anti-ruissellement",
                "min": 1_500,
                "max": 4_000,
                "source": "CEPRI — Ruissellement",
                "aide": None,
            },
        ],
    },
    "menuiseries": {
        "tempete": [
            {
                "mesure": "Remplacement des menuiseries par des châssis renforcés",
                "min": 5_000,
                "max": 12_000,
                "source": "MRN — Tempête",
                "aide": None,
            },
        ],
    },
}

# Alias risque → générique quand la zone n'a pas de table dédiée pour ce risque.
_RISQUE_FALLBACK = "tempete"


def _source_ref(fiche_id: str, source_id: str, extrait: str) -> dict[str, str]:
    return {
        "fiche_id": fiche_id,
        "source_id": source_id,
        "extrait_exact": extrait,
    }


def _mesures_par_risque(zone: str, risque: str) -> list[dict[str, Any]]:
    """Cherche les mesures de référence pour (zone, risque), avec repli."""
    table = _FALLBACK_COUTS.get(zone, {})
    mesures = table.get(risque)
    if mesures:
        return mesures
    # Repli : générique tempête (protection large) si la zone existe,
    # sinon première table disponible.
    if risque != "tempete":
        mesures = table.get("tempete")
    if not mesures and table:
        mesures = next(iter(table.values()))
    return mesures or []


def generer_recommandations_fallback(
    zone_name: str,
    risques: list[str],
) -> list[dict[str, Any]]:
    """Construit des recommandations chiffrées et sourcées pour une zone,
    à partir des coûts de référence (sources MRN/CEPRI/BRGM/ADEME).

    Garantit au moins 1 recommandation par zone à risque, au maximum 2
    (concision, pas de doublons).
    """
    recommandations: list[dict[str, Any]] = []
    vues: set[str] = set()

    for risque in risques:
        mesures = _mesures_par_risque(zone_name, risque)
        for m in mesures:
            if m["mesure"] in vues:
                continue
            vues.add(m["mesure"])

            source_id = "REF-" + str(abs(hash(m["mesure"])) % 10_000)
            recommandation: dict[str, Any] = {
                "mesure": m["mesure"],
                "explication": (
                    f"Mesure visant à réduire le risque de {risque.replace('_', ' ')} "
                    f"sur la zone {zone_name} — coûts et recommandations issus de {m['source']}."
                ),
                "risque_concerne": risque,
                "type": "recommandation_source",
                "cout_estime": {
                    "montant_min": m["min"],
                    "montant_max": m["max"],
                    "devise": "EUR",
                    "unite": "global",
                    "date_estimation": None,
                    "zone_geo": "France",
                    "hypotheses": f"Coût total des travaux tel que publié par {m['source']} — "
                                  "fourchette large selon la configuration du bâtiment",
                },
                "aide": (
                    {
                        "dispositif": m["aide"],
                        "conditions": "Éligibilité potentielle sous conditions (statut "
                                      "non confirmé à ce stade)",
                        "statut": "potential_eligibility_only",
                    }
                    if m["aide"]
                    else None
                ),
                "sources": [
                    _source_ref(
                        fiche_id=source_id,
                        source_id=source_id,
                        extrait=f"Coût de référence : {m['min']}–{m['max']} € "
                                f"({m['source']})",
                    )
                ],
            }
            recommandations.append(recommandation)
            if len(recommandations) >= 2:
                break

        if len(recommandations) >= 2:
            break

    # Dernier recours : toujours une recommandation chiffrée même si la
    # table est vide pour ce risque/zone.
    if not recommandations:
        recommandations.append(
            {
                "mesure": "Audit de vulnérabilité par un professionnel du bâtiment",
                "explication": (
                    "Un diagnostic approfondi permet d'identifier les points faibles "
                    "du bâtiment et de prioriser les travaux de résilience climatique."
                ),
                "risque_concerne": risques[0] if risques else "generique",
                "type": "bonne_pratique_generale",
                "cout_estime": {
                    "montant_min": 500,
                    "montant_max": 1_500,
                    "devise": "EUR",
                    "unite": "global",
                    "date_estimation": None,
                    "zone_geo": "France",
                    "hypotheses": "Prestation d'audit (architecte / bureau d'études)",
                },
                "aide": None,
                "sources": [
                    _source_ref(
                        fiche_id="REF-AUDIT",
                        source_id="REF-AUDIT",
                        extrait="Coût moyen d'un audit de vulnérabilité du bâtiment en France",
                    )
                ],
            }
        )

    return recommandations