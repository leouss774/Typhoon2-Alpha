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
            timeout_ms=config.API_TIMEOUT * 1000,
        )
    return _client


def chat_json(system_prompt: str, user_prompt: str, max_retries: int = 3) -> dict:
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
            return json.loads(content)
        except Exception as e:
            last_err = e
            print(f"    [retry {attempt + 1}/{max_retries}] erreur: {e}")
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Echec appel Mistral (chat) apres {max_retries} tentatives: {last_err}")


def embed_texts(texts: list) -> list:
    """Retourne la liste des vecteurs d'embedding pour une liste de textes."""
    client = get_client()
    response = client.embeddings.create(model=config.EMBED_MODEL, inputs=texts)
    return [item.embedding for item in response.data]
