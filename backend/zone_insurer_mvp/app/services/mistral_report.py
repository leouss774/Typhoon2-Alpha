from __future__ import annotations

import asyncio
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger
from app.services.mistral_client import chat_json

logger = get_logger(__name__)

_SYSTEM_PROMPT = """Tu es un analyste risques pour un assureur. On te donne un resume
statistique d'une zone (plusieurs points/batiments evalues). Reponds UNIQUEMENT en JSON :
{
  "narrative": "2-4 phrases, ton factuel souscription",
  "recommendations": ["...", "..."]
}
Ne invente aucune donnee absente du bloc utilisateur. 3 a 5 recommandations max,
orientees prime/souscription (pas travaux de renovation detailles)."""


def _fallback(agg: dict[str, Any]) -> dict[str, Any]:
    return {
        "narrative": agg.get("narrative") or "",
        "recommendations": agg.get("recommendations") or [],
    }


def _build_user_prompt(agg: dict[str, Any]) -> str:
    lines = [
        f"Points OK: {agg.get('nb_ok', 0)}, echecs: {agg.get('nb_errors', 0)}",
        f"Score zone: {agg.get('aggregate_score')}/100, tier {agg.get('aggregate_tier')}",
    ]
    for h in agg.get("hazard_breakdown") or []:
        ms = h.get("mean_score")
        extra = f", score moyen {ms}" if ms is not None else ""
        lines.append(
            f"- {h['label']}: {h['pct_present']}% des points, niveaux {h.get('levels', [])}{extra}"
        )
    cat = agg.get("catnat_totals") or {}
    lines.append(
        f"CATNAT (arretes): inondation={cat.get('inondation', 0)}, "
        f"secheresse={cat.get('secheresse', 0)}, mouvement={cat.get('mouvement_terrain', 0)}"
    )
    top = sorted(
        agg.get("buildings") or [],
        key=lambda b: b.get("score_global") or 0,
        reverse=True,
    )[:5]
    for b in top:
        haz = ", ".join(
            f"{x['hazard']}({x.get('score', '?')})"
            for x in (b.get("hazards") or [])
            if x.get("level")
        )
        lines.append(
            f"Point {b.get('address_label') or 'coord'}: score {b.get('score_global', 0)} — {haz}"
        )
    return "\n".join(lines)


async def generate(agg: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Returns (narrative_payload, narrative_source)."""
    if not settings.mistral_enabled or not settings.mistral_api_key:
        return _fallback(agg), "template"

    try:
        user = _build_user_prompt(agg)
        result = await asyncio.to_thread(chat_json, _SYSTEM_PROMPT, user)
        if not isinstance(result, dict) or "narrative" not in result or "recommendations" not in result:
            raise ValueError(f"reponse Mistral inattendue: {result!r}")
        return result, "mistral"
    except Exception as exc:
        logger.warning("mistral_report echec (%s), repli template", exc)
        return _fallback(agg), "template"
