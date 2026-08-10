"""
Rapport narratif complet Mistral IA pour le flux /diagnostic/adresse/rapport.

Règles strictes (addendum §4) :
  1. Le prompt Mistral ne reçoit QUE RisqueReport.model_dump() — jamais les
     données Géorisques brutes.
  2. N'invente AUCUNE date, AUCUN chiffre, AUCUN fait absent du JSON fourni.
  3. Génération en un seul appel Mistral (RapportNarratif structuré).
  4. Toute erreur ou timeout Mistral → retourne (None, cause) (fail-soft, la
     cause permet à l'API de renvoyer une erreur 502/503 explicite).
  5. Ce module est synchrone (SDK mistralai) et doit être appelé via
     asyncio.to_thread() depuis le handler FastAPI async.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.risque_report import RisqueReport

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Schémas du rapport narratif
# ---------------------------------------------------------------------------

class SectionRapport(BaseModel):
    titre: str
    contenu: str  # 2-4 phrases factuelles, basées uniquement sur le JSON
    aleas_associes: list[str] = []  # ex: ["inondation", "rga"]


class RapportNarratif(BaseModel):
    introduction: str  # 2-3 phrases de cadrage
    sections: list[SectionRapport]
    synthese_finale: str  # hiérarchisation des risques
    obligations_reglementaires: list[str] | None = None
    genere_par: str = "mistral-large-latest"
    metadata: dict[str, Any] = {}
    avertissement_ia: str = (
        "Ce rapport est généré automatiquement par IA à partir des données publiques "
        "Géorisques normalisées. Il ne remplace pas l'ERRIAL ni l'avis d'un expert."
    )


# ---------------------------------------------------------------------------
# Prompt Système
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT_RAPPORT = """
Tu es un expert en prévention des risques naturels et technologiques immobiliers en France.
Tu rédiges un rapport narratif complet, professionnel et factuel en français à partir d'un JSON
de diagnostic géo-risque déjà normalisé (source : Géorisques BRGM/MTE).

RÈGLES STRICTES :
- Une section par aléa présent (present=true) ou pour l'historique CatNat.
- N'invente AUCUNE date, AUCUN chiffre, AUCUN fait absent du JSON fourni.
- Ne fais référence à aucune étude ou mesure non citée dans le JSON.
- Réponds UNIQUEMENT en JSON valide respectant le schéma ci-dessous, sans texte avant ni après.

Format JSON attendu :
{
  "introduction": "...",
  "sections": [
    {
      "titre": "...",
      "contenu": "...",
      "aleas_associes": ["code_alea"]
    }
  ],
  "synthese_finale": "...",
  "obligations_reglementaires": ["..."]
}
""".strip()


def _build_rapport_prompt(report: RisqueReport) -> str:
    """Filtre RisqueReport.model_dump() pour ne transmettre que les faits utiles au rapport."""
    data = report.model_dump()
    aleas_propres = []
    for a in data.get("aleas", []):
        if a.get("present") is True or a.get("catnat_historique"):
            aleas_propres.append({
                "code": a.get("code"),
                "libelle": a.get("libelle"),
                "niveau": a.get("niveau"),
                "zonage": a.get("zonage"),
                "nombre_catnat": len(a.get("catnat_historique") or []),
                "catnat_exemples": [
                    {
                        "libelle": c.get("libelle_risque_jo"),
                        "date_debut": c.get("date_debut_evt"),
                        "date_fin": c.get("date_fin_evt"),
                    }
                    for c in (a.get("catnat_historique") or [])[:5]
                ],
            })

    prompt_data = {
        "adresse": data.get("adresse_normalisee"),
        "code_insee": data.get("code_insee"),
        "date_rapport": str(data.get("date_generation")),
        "aleas_presents": aleas_propres,
    }
    return json.dumps(prompt_data, ensure_ascii=False, indent=2)


def _cause_mistral(exc: Exception) -> str:
    """Cause courte et sûre d'un échec Mistral (jamais de secret)."""
    msg = str(exc).strip()[:200]
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


def _appeler_mistral_narratif_sync(report: RisqueReport) -> tuple[RapportNarratif | None, str | None]:
    """Retourne (rapport, cause) — cause est un code de raison machine court
    quand le rapport n'a pas pu être généré (None si succès). Codes possibles :
    `api_key_manquante`, `import_echec`, `mistral_erreur`, `reponse_malformee`,
    ou la description courte d'une erreur Mistral."""
    if not settings.mistral_api_key:
        logger.debug("MISTRAL_API_KEY absent — rapport narratif indisponible")
        return None, "api_key_manquante"

    try:
        from app.recommandations.mistral_client import chat_json
    except ImportError as exc:
        logger.warning("mistralai non disponible — rapport narratif ignoré : %s", exc)
        return None, "import_echec"

    user_prompt = _build_rapport_prompt(report)
    t0 = time.perf_counter()

    try:
        reponse = chat_json(
            system_prompt=_SYSTEM_PROMPT_RAPPORT,
            user_prompt=user_prompt,
            max_retries=2,
            # Le rapport (intro + sections + synthèse + obligations) dépasse
            # facilement les 1000 tokens par défaut : la réponse était tronquée
            # en plein JSON ("Unterminated string", erreur 502).
            max_tokens=4000,
        )
    except Exception as exc:
        logger.warning("Mistral échec rapport narratif pour %r : %s", report.adresse_normalisee, exc)
        return None, f"mistral_erreur: {_cause_mistral(exc)}"

    latence_ms = round((time.perf_counter() - t0) * 1000)

    try:
        sections = [
            SectionRapport(
                titre=s.get("titre", "Analyse"),
                contenu=s.get("contenu", ""),
                aleas_associes=s.get("aleas_associes", []),
            )
            for s in reponse.get("sections", [])
        ]
        return (
            RapportNarratif(
                introduction=reponse.get("introduction", ""),
                sections=sections,
                synthese_finale=reponse.get("synthese_finale", ""),
                obligations_reglementaires=reponse.get("obligations_reglementaires"),
                genere_par="mistral-large-latest",
                metadata={"latence_ms": latence_ms},
            ),
            None,
        )
    except Exception as exc:
        logger.warning("Réponse Mistral rapport narratif malformée : %s", exc)
        return None, "reponse_malformee"


async def generer_rapport_narratif(report: RisqueReport) -> tuple[RapportNarratif | None, str | None]:
    """Point d'entrée async pour le rapport narratif : (rapport, cause)."""
    try:
        return await asyncio.to_thread(_appeler_mistral_narratif_sync, report)
    except Exception as exc:
        logger.warning("Erreur inattendue rapport narratif : %s", exc)
        return None, f"erreur_inattendue: {_cause_mistral(exc)}"
