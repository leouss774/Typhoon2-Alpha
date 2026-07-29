from __future__ import annotations

import json
import time

from mistralai.client import Mistral

from app.core.config import settings

CHAT_MODEL = "mistral-large-latest"
REQUEST_TIMEOUT_MS = 120_000
CHAT_MAX_TOKENS = 2000


def chat_json(system_prompt: str, user_prompt: str, max_retries: int = 3) -> dict:
    if not settings.mistral_api_key:
        raise RuntimeError("MISTRAL_API_KEY manquant")
    client = Mistral(api_key=settings.mistral_api_key, timeout_ms=REQUEST_TIMEOUT_MS)
    last_err: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.chat.complete(
                model=CHAT_MODEL,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=CHAT_MAX_TOKENS,
            )
            content = response.choices[0].message.content
            return json.loads(content)
        except Exception as e:
            last_err = e
            time.sleep(3 * (attempt + 1))
    raise RuntimeError(f"Echec appel Mistral apres {max_retries} tentatives: {last_err}")
