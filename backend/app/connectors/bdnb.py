"""Connecteur BDNB (Base de Données Nationale des Bâtiments).

API publique : https://api.bdnb.io
"""

from __future__ import annotations

import httpx
from app.core.config import settings


class BdnbAdresseIntrouvable(Exception):
    pass


async def fetch_bdnb(client: httpx.AsyncClient, address: str) -> dict | None:
    """Interroge la BDNB pour une adresse donnée."""
    headers = {}
    if settings.bdnb_api_key:
        headers["X-API-Key"] = settings.bdnb_api_key

    try:
        response = await client.get(
            f"{settings.bdnb_base_url}/v1/batiments",
            params={"adresse": address, "limit": 1},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

        if not data or not data.get("results"):
            raise BdnbAdresseIntrouvable(f"Aucun bâtiment trouvé pour {address!r}")

        return data["results"][0]

    except httpx.HTTPStatusError as e:
        if e.response.status_code in (404, 400):
            raise BdnbAdresseIntrouvable(f"BDNB introuvable pour {address!r}")
        raise
