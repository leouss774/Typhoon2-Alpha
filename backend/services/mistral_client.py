"""
mistral_client.py
------------------
Appel API Mistral basique (chat completions) + logique de retry si la
réponse n'est pas un JSON valide selon le schéma attendu.

Fonctionne en 2 modes :
- réel : appelle l'API Mistral avec la clé définie dans .env
- mock (USE_MOCK_MISTRAL=true, ou clé absente) : renvoie une réponse simulée
  pour développer/tester l'UI sans dépendre du réseau ni d'une clé valide.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from backend.config import settings
from backend.services.json_validator import (
    JsonExtractionError,
    build_retry_prompt,
    parse_and_validate,
)

logger = logging.getLogger("jumeau_numerique.mistral")

T = TypeVar("T", bound=BaseModel)


class MistralCallError(RuntimeError):
    """Levée si l'appel API échoue (réseau, auth, etc.) ou si la sortie reste
    invalide après toutes les tentatives de retry."""


def _mock_completion(system_prompt: str, user_prompt: str) -> str:
    """
    Réponse simulée minimaliste utilisée quand USE_MOCK_MISTRAL=true ou
    qu'aucune clé API n'est configurée. Ne cherche pas à être "intelligente" :
    sert uniquement à ne pas bloquer le développement front / des autres
    modules en attendant une vraie clé API.
    """
    logger.warning("MISTRAL MOCK: aucune clé API réelle utilisée pour cet appel.")
    if "test de vulnérabilité" in system_prompt.lower() or "score_apres_travaux" in system_prompt.lower():
        return """{
  "zone": "toiture",
  "scenario": "Canicule de 8 semaines suivie d'un épisode pluvieux intense (simulation).",
  "score_avant": 55,
  "score_apres_travaux": 33,
  "resume": "Sans travaux, la toiture accumule un stress thermique important qui accélère sa dégradation. Une isolation renforcée limite nettement ce risque.",
  "points_de_vigilance": ["Vérifier l'état de la sous-toiture après chaque épisode caniculaire", "Prévoir une ventilation de toiture adaptée"]
}"""
    return """{
  "score_global": 62,
  "zones": {
    "fondations": {"risque": 88, "niveau": "critique", "alea_principal": "RGA aggravé (simulation)", "justification": "Sécheresses plus longues d'ici 2050.", "recommandations": []},
    "murs_nord": {"risque": 45, "niveau": "modere", "alea_principal": "Infiltration accrue (simulation)", "justification": "Précipitations hivernales plus intenses.", "recommandations": []},
    "murs_sud": {"risque": 38, "niveau": "modere", "alea_principal": "Stress thermique (simulation)", "justification": "Canicules plus longues.", "recommandations": []},
    "murs_est": {"risque": 30, "niveau": "modere", "alea_principal": "Vent (simulation)", "justification": "Intensification modérée.", "recommandations": []},
    "murs_ouest": {"risque": 50, "niveau": "modere", "alea_principal": "Intempéries (simulation)", "justification": "Aggravation attendue.", "recommandations": []},
    "toiture": {"risque": 75, "niveau": "eleve", "alea_principal": "Canicule prolongée (simulation)", "justification": "Isolation actuelle insuffisante.", "recommandations": []},
    "sous_sol": {"risque": 80, "niveau": "eleve", "alea_principal": "Inondation aggravée (simulation)", "justification": "Hausse des sinistres climatiques attendue.", "recommandations": []}
  }
}"""


def _call_mistral_api(system_prompt: str, user_prompt: str) -> str:
    """Appel HTTP réel à l'API Mistral. Renvoie le texte brut de la réponse."""
    if not settings.mistral_api_key:
        raise MistralCallError(
            "MISTRAL_API_KEY absente : renseignez .env ou activez USE_MOCK_MISTRAL=true pour tester."
        )

    payload = {
        "model": settings.mistral_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.3,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {settings.mistral_api_key}",
        "Content-Type": "application/json",
    }

    try:
        with httpx.Client(timeout=settings.mistral_timeout_seconds) as client:
            response = client.post(settings.mistral_api_url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPStatusError as exc:
        raise MistralCallError(f"Erreur API Mistral ({exc.response.status_code}): {exc.response.text}") from exc
    except httpx.RequestError as exc:
        raise MistralCallError(f"Erreur réseau lors de l'appel Mistral : {exc}") from exc

    try:
        return data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise MistralCallError(f"Réponse Mistral inattendue : {data}") from exc


def call_mistral_and_validate(
    system_prompt: str,
    user_prompt: str,
    schema: type[T],
) -> T:
    """
    Appelle Mistral (ou le mock) puis valide la sortie contre `schema`.
    En cas de JSON invalide, renvoie automatiquement un prompt d'erreur à
    Mistral pour qu'il corrige sa réponse, jusqu'à `settings.mistral_max_retries`
    tentatives. Lève MistralCallError si tout échoue.
    """
    completion_fn = _mock_completion if settings.use_mock_mistral or not settings.mistral_api_key else _call_mistral_api

    raw_text = completion_fn(system_prompt, user_prompt)
    attempt = 0
    last_error: Exception | None = None

    while attempt <= settings.mistral_max_retries:
        try:
            return parse_and_validate(raw_text, schema)
        except (JsonExtractionError, ValidationError) as exc:
            last_error = exc
            logger.warning("Sortie Mistral invalide (tentative %s/%s) : %s",
                            attempt + 1, settings.mistral_max_retries + 1, exc)
            attempt += 1
            if attempt > settings.mistral_max_retries:
                break
            retry_prompt = build_retry_prompt(exc, raw_text)
            raw_text = completion_fn(system_prompt, f"{user_prompt}\n\n---\n{retry_prompt}")

    raise MistralCallError(
        f"Impossible d'obtenir une sortie Mistral valide après {settings.mistral_max_retries + 1} tentative(s) : {last_error}"
    )
