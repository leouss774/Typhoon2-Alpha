"""
json_validator.py
------------------
Extrait un objet JSON depuis la réponse texte de Mistral (qui peut contenir
des ```fences```, du texte d'intro/conclusion, ou plusieurs blocs JSON) et le
valide contre un schéma Pydantic. Fournit aussi la logique de fallback si la
sortie est invalide (utilisée par le module Mistral pour le test de
vulnérabilité et la projection 2050 -- indépendant du reste, testable seul).
"""

from __future__ import annotations

import json
import re
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)


class JsonExtractionError(ValueError):
    """Aucun JSON exploitable trouvé dans la réponse du modèle."""


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _candidate_blocks(raw_text: str) -> list[str]:
    """Retourne, par ordre de priorité, les blocs de texte susceptibles de contenir le JSON."""
    candidates: list[str] = []

    # 1. Contenu des blocs ```json ... ``` (le plus fiable, Mistral les utilise souvent)
    candidates.extend(m.strip() for m in _FENCE_RE.findall(raw_text))

    # 2. Le plus grand segment { ... } équilibré trouvé dans le texte brut
    #    (utile si Mistral ajoute une phrase avant/après sans fences)
    depth = 0
    start = None
    best: tuple[int, int] | None = None
    for i, ch in enumerate(raw_text):
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    if best is None or (i - start) > (best[1] - best[0]):
                        best = (start, i + 1)
    if best:
        candidates.append(raw_text[best[0]:best[1]])

    # 3. Le texte entier tel quel, en dernier recours
    candidates.append(raw_text.strip())

    return candidates


def extract_json(raw_text: str) -> dict[str, Any]:
    """
    Essaie plusieurs stratégies pour isoler un unique objet JSON valide dans
    une réponse Mistral potentiellement bruitée (markdown, texte parasite,
    guillemets typographiques, virgules finales).
    """
    if not raw_text or not raw_text.strip():
        raise JsonExtractionError("Réponse vide")

    last_error: Exception | None = None
    for block in _candidate_blocks(raw_text):
        cleaned = block.strip()
        if not cleaned:
            continue
        # Nettoyages usuels des sorties LLM avant de retenter le parsing strict
        cleaned = cleaned.replace("“", '"').replace("”", '"').replace("’", "'")
        cleaned = re.sub(r",\s*([}\]])", r"\1", cleaned)  # virgules finales
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue

    raise JsonExtractionError(f"Aucun JSON valide trouvé dans la réponse : {last_error}")


def parse_and_validate(raw_text: str, schema: type[T]) -> T:
    """Extrait le JSON puis le valide contre un modèle Pydantic. Lève en cas d'échec."""
    data = extract_json(raw_text)
    return schema.model_validate(data)


def safe_parse_with_fallback(
    raw_text: str,
    schema: type[T],
    fallback: T,
) -> tuple[T, bool]:
    """
    Variante non bloquante : retourne (résultat, ok).
    Si le parsing/la validation échoue, retourne le fallback fourni par
    l'appelant et ok=False, plutôt que de lever une exception -- l'appelant
    décide alors s'il retente l'appel Mistral (avec un prompt d'erreur) ou
    s'il affiche directement le fallback à l'utilisateur.
    """
    try:
        return parse_and_validate(raw_text, schema), True
    except (JsonExtractionError, ValidationError):
        return fallback, False


def build_retry_prompt(original_error: Exception, raw_text: str) -> str:
    """
    Construit un message d'erreur à renvoyer à Mistral pour qu'il corrige sa
    sortie, utilisé par mistral_client.call_with_retry().
    """
    return (
        "Ta réponse précédente n'était pas un JSON valide selon le schéma demandé.\n"
        f"Erreur de validation : {original_error}\n\n"
        "Réponse précédente (tronquée) :\n"
        f"{raw_text[:500]}\n\n"
        "Corrige et renvoie UNIQUEMENT le JSON valide, sans texte autour, "
        "sans balises markdown, en respectant strictement le schéma fourni "
        "dans les instructions initiales."
    )


if __name__ == "__main__":
    # Auto-test rapide avec quelques réponses "sales" typiques d'un LLM
    samples = [
        '```json\n{"a": 1, "b": 2,}\n```',
        'Voici le résultat :\n```json\n{"zone": "toiture", "score_avant": 55}\n```\nBonne journée !',
        '{"zone": "toiture", "score_avant": 55, "score_apres_travaux": 30}',
        'Désolé je ne peux pas répondre en JSON.',
    ]
    for s in samples:
        try:
            print(extract_json(s))
        except JsonExtractionError as e:
            print("ECHEC:", e)
