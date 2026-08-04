import json
import time

from mistralai.client import Mistral

import config

_client = None


def get_client():
    global _client
    if _client is None:
        if not config.MISTRAL_API_KEY:
            raise RuntimeError(
                "MISTRAL_API_KEY manquant. Cree un fichier .env a la racine "
                "avec la ligne: MISTRAL_API_KEY=ta_cle"
            )
        _client = Mistral(
            api_key=config.MISTRAL_API_KEY,
            timeout_ms=config.REQUEST_TIMEOUT_MS,
        )
    return _client

def _is_rate_limit_error(e: Exception) -> bool:
    msg = str(e).lower()
    return "429" in msg or "rate_limited" in msg or "rate limit" in msg


def _backoff_seconds(e: Exception, attempt: int) -> float:
    if _is_rate_limit_error(e):
        return min(60, 20 * (attempt + 1))
    return 5 * (attempt + 1)

def chat_json(system_prompt: str, user_prompt: str, max_retries: int = 5) -> dict:
    """Appelle le modele de chat Mistral et force une reponse JSON."""
    client = get_client()
    last_err = None
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=config.CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
            )
            content = response.choices[0].message.content
            time.sleep(config.THROTTLE_SECONDS)
            return json.loads(content)
        except Exception as e:
            last_err = e
            wait = _backoff_seconds(e, attempt)
            print(f"    [retry {attempt + 1}/{max_retries}] erreur: {e}")
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (chat) apres {max_retries} tentatives: {last_err}")


def embed_texts(texts: list, max_retries: int = 5) -> list:
    client = get_client()
    last_err = None
    for attempt in range(max_retries):
        try:
            response = client.embeddings.create(model=config.EMBED_MODEL, inputs=texts)
            time.sleep(config.THROTTLE_SECONDS)
            return [item.embedding for item in response.data]
        except Exception as e:
            last_err = e
            wait = _backoff_seconds(e, attempt)
            print(f"    [retry embeddings {attempt + 1}/{max_retries}] erreur: {e}")
            print(f"    -> attente {wait:.0f}s avant nouvelle tentative")
            time.sleep(wait)
    raise RuntimeError(f"Echec appel Mistral (embeddings) apres {max_retries} tentatives: {last_err}")
