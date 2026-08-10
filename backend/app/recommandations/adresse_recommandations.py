"""
Recommandations Mistral IA pour le flux /diagnostic/adresse.

Règles strictes (audit §2.4 + plan Sprint B) :
  1. Le prompt Mistral ne reçoit QUE RisqueReport.model_dump() — jamais les
     données Géorisques brutes (cavites, mvt, etc.).
  2. Toute erreur ou timeout Mistral → retourne None sans propager l'exception.
  3. Ce module est synchrone (SDK mistralai) et doit être appelé via
     asyncio.to_thread() depuis le handler FastAPI async.
  4. Si MISTRAL_API_KEY est absent → retourne None immédiatement, sans log ERROR.

Point d'entrée unique : recommander(report: RisqueReport) -> RecommandationsIA | None
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.risque_report import RecommandationsIA, RisqueReport

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Prompt système — compact, orienté action, pas de reformulation de la data
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """
Tu es un conseiller immobilier expert en risques naturels et technologiques
en France. On te fournit un rapport de diagnostic géo-risque structuré
(format JSON, source : Géorisques BRGM/MTE) pour une adresse donnée.

Règles impératives :
- Réponds UNIQUEMENT en JSON valide, sans texte avant ni après.
- Limite le champ "resume" à 2 phrases maximum.
- Limite "actions_prioritaires" à 5 éléments maximum, ordonnés par urgence.
- Limite "points_vigilance" à 3 éléments maximum.
- Ne mentionne JAMAIS de scores numériques exacts issus du rapport.
- Ne génère AUCUNE information absente du rapport (pas d'hallucination).
- Si tous les aléas sont "tres_faible" ou absent, dis-le explicitement
  dans resume plutôt que d'inventer des recommandations inutiles.

Format de sortie JSON attendu (strictement) :
{
  "resume": "...",
  "actions_prioritaires": ["...", "..."],
  "points_vigilance": ["...", "..."]
}
""".strip()


def _build_user_prompt(report: RisqueReport) -> str:
    """Construit le prompt utilisateur à partir du RisqueReport sérialisé.

    On filtre les champs volumineux ou non pertinents pour le prompt :
    - catnat_historique (trop long, l'info utile est déjà dans 'present'/'niveau')
    - erreurs_partielles (information technique, pas métier)
    - avertissement (boilerplate)
    - recommandations (champ vide qu'on est en train de remplir)
    """
    data = report.model_dump()
    # Nettoyage : on garde seulement ce qui est utile pour le conseil
    aleas_propres = []
    for a in data.get("aleas", []):
        aleas_propres.append({
            "code": a.get("code"),
            "libelle": a.get("libelle"),
            "present": a.get("present"),
            "niveau": a.get("niveau"),
            "zonage": a.get("zonage"),
            # catnat_historique volontairement absent du prompt
        })

    prompt_data = {
        "adresse": data.get("adresse_normalisee"),
        "code_insee": data.get("code_insee"),
        "date_rapport": str(data.get("date_generation")),
        "nombre_aleas_presents": data.get("alea_count"),
        "aleas": aleas_propres,
    }
    return json.dumps(prompt_data, ensure_ascii=False, indent=2)


def _appeler_mistral_sync(report: RisqueReport) -> RecommandationsIA | None:
    """Appel synchrone Mistral (doit être wrappé dans asyncio.to_thread)."""
    if not settings.mistral_api_key:
        logger.debug("MISTRAL_API_KEY absent — recommandations ignorées pour %r", report.adresse_normalisee)
        return None

    # Import local pour ne pas crasher si mistralai n'est pas installé
    try:
        from app.recommandations.mistral_client import chat_json
    except ImportError as exc:
        logger.warning("mistralai non disponible — recommandations ignorées : %s", exc)
        return None

    user_prompt = _build_user_prompt(report)
    t0 = time.perf_counter()

    try:
        reponse = chat_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            max_retries=2,   # Sprint B : fail-fast sur /diagnostic/adresse
        )
    except Exception as exc:
        logger.warning(
            "Mistral échec pour %r — recommandations=None : %s",
            report.adresse_normalisee, exc,
        )
        return None

    latence_ms = round((time.perf_counter() - t0) * 1000)

    try:
        return RecommandationsIA(
            resume=reponse.get("resume", ""),
            actions_prioritaires=reponse.get("actions_prioritaires", []),
            points_vigilance=reponse.get("points_vigilance", []),
            metadata={"latence_ms": latence_ms},
        )
    except Exception as exc:
        logger.warning(
            "Réponse Mistral malformée pour %r — recommandations=None : %s",
            report.adresse_normalisee, exc,
        )
        return None


async def recommander(report: RisqueReport) -> RecommandationsIA | None:
    """
    Point d'entrée async pour le handler FastAPI.

    Appelle Mistral dans un thread dédié pour ne pas bloquer la boucle asyncio.
    Toujours fail-soft : retourne None en cas d'erreur, jamais une exception.
    """
    try:
        return await asyncio.to_thread(_appeler_mistral_sync, report)
    except Exception as exc:
        # Filet de sécurité : asyncio.to_thread ne devrait pas propager,
        # mais on ne prend aucun risque.
        logger.warning(
            "Erreur inattendue recommandations pour %r : %s",
            report.adresse_normalisee, exc,
        )
        return None
