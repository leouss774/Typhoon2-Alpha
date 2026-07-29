"""
mistral_report — AI-generated narrative + tailored recommendations for the
zone insurer report, reusing the sibling recommandations agent's Mistral
client (app/recommandations/mistral_client.py: same MISTRAL_API_KEY, same
chat_json(system_prompt, user_prompt) -> dict pattern, same retry/backoff).

Deterministic fallback (no API key, or the call fails) reuses the phase-1
templated recommendations, so the zone report is never blocked on Mistral
being configured.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.mistral_client import chat_json

logger = get_logger(__name__)

_FALLBACK_RECOMMENDATIONS = {
    "critique": [
        "Prioriser une inspection individuelle sur site pour chaque actif flagge avant toute souscription.",
        "Envisager une exclusion ou surprime ciblee sur le ou les alea(s) dominant(s) identifies.",
    ],
    "eleve": [
        "Demander une etude de sol / diagnostic structurel pour les actifs proches du seuil critique.",
        "Prevoir une clause de franchise renforcee sur l'alea dominant de la zone.",
    ],
    "modere": [
        "Suivi standard suffisant ; revisiter la zone lors du prochain renouvellement.",
    ],
    "faible": [
        "Aucune action specifique requise au-dela du suivi standard.",
    ],
}

_SYSTEM_PROMPT = """Tu es un analyste risques pour un assureur. On te donne un
resume statistique d'une zone geographique (plusieurs batiments evalues pour
des risques climatiques et de mouvement de terrain). Reponds UNIQUEMENT en
JSON avec exactement ces cles :
{
  "narrative": "2-4 phrases resumant le profil de risque de la zone, ton factuel et professionnel",
  "recommendations": ["recommandation 1", "recommandation 2", ...]
}
Les recommandations doivent etre concretes, orientees souscription/prime
(pas des travaux de renovation detailles - ca c'est le role d'un autre outil),
et tenir compte du tier agrege, des alea(s) dominant(s), et de l'historique
CATNAT si pertinent. 3 a 5 recommandations maximum."""


def _fallback(aggregate: dict[str, Any]) -> dict[str, Any]:
    tier = aggregate["aggregate_tier"]
    return {
        "narrative": (
            f"Zone évaluée à un niveau de risque {tier} "
            f"(score agrégé {aggregate['aggregate_score']}/100 sur {aggregate['nb_ok']} bâtiment(s) analysé(s))."
        ),
        "recommendations": _FALLBACK_RECOMMENDATIONS.get(tier, []),
    }


def _build_user_prompt(aggregate: dict[str, Any]) -> str:
    hazard_lines = "\n".join(
        f"- {h['hazard']}: moyenne {h['mean_score']}/100, {h['pct_high_or_critical']}% des bâtiments en élevé/critique"
        for h in aggregate["hazard_breakdown"]
    )
    catnat = aggregate.get("catnat_totals") or {}
    top_flagged = ", ".join(
        b["address_label"] or f"{b['lat']:.4f},{b['lon']:.4f}" for b in aggregate["flagged_buildings"][:5]
    )
    return f"""Zone : {aggregate['nb_ok']} bâtiment(s) évalué(s) avec succès sur {aggregate['nb_buildings']}.
Score agrégé : {aggregate['aggregate_score']}/100 (tier {aggregate['aggregate_tier']}).
Nombre de bâtiments flaggés pour revue individuelle : {len(aggregate['flagged_buildings'])}.

Répartition par aléa :
{hazard_lines}

Historique CATNAT (arrêtés de catastrophe naturelle déclarés) :
inondation={catnat.get('inondation', 0)}, sécheresse={catnat.get('secheresse', 0)}, mouvement de terrain={catnat.get('mouvement_terrain', 0)}

Bâtiments les plus à risque : {top_flagged or "aucun"}"""


async def generate(aggregate: dict[str, Any]) -> dict[str, Any]:
    """Returns {"narrative": str, "recommendations": list[str]}.

    Falls back to the deterministic template if MISTRAL_API_KEY isn't set
    or the call fails for any reason — a zone report should never fail
    just because the AI narrative layer is unavailable.
    """
    if not settings.mistral_api_key:
        logger.info("mistral_report -- MISTRAL_API_KEY absent, repli deterministe")
        return _fallback(aggregate)

    try:
        user_prompt = _build_user_prompt(aggregate)
        result = await asyncio.to_thread(chat_json, _SYSTEM_PROMPT, user_prompt)
        if not isinstance(result, dict) or "narrative" not in result or "recommendations" not in result:
            raise ValueError(f"forme de reponse Mistral inattendue: {result!r}")
        return result
    except Exception as exc:
        logger.warning("mistral_report -- echec generation IA (%s), repli deterministe", exc)
        return _fallback(aggregate)
