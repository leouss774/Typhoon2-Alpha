"""Altimétrie via l'API Géoplateforme IGN.

https://data.geopf.fr/altimetrie/1.0
"""

from __future__ import annotations

import httpx
from app.core.config import settings


async def fetch_altitude(client: httpx.AsyncClient, lat: float, lon: float) -> float | None:
    """Récupère l'altitude en mètres pour un point donné."""
    try:
        response = await client.get(
            f"{settings.ign_altitude_base_url}/elevation",
            params={
                "lon": lon,
                "lat": lat,
                "indent": "false",
            },
        )
        response.raise_for_status()
        data = response.json()
        elevations = data.get("elevations", [])
        if elevations:
            return float(elevations[0].get("z", 0))
        return None
    except httpx.HTTPError:
        return None
