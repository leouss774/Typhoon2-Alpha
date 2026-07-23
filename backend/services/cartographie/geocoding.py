"""Service de géocodage d'adresses.

Convertit une adresse postale en coordonnées géographiques (lat, lng)
et enrichit avec des données contextuelles (altitude, zonages, etc.).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


async def geocoder_adresse(adresse: str, provider: str = "ban") -> dict[str, Any]:
    """Géocode une adresse postale française.

    Args:
        adresse: Adresse postale complète.
        provider: Fournisseur de géocodage ('ban' | 'mapbox' | 'openstreetmap').

    Returns:
        Dict avec coordonnées et métadonnées.
    """
    if provider == "ban":
        return await _geocoder_ban(adresse)
    elif provider == "openstreetmap":
        return await _geocoder_osm(adresse)
    else:
        logger.warning(f"Provider {provider} non supporté, fallback BAN")
        return await _geocoder_ban(adresse)


async def _geocoder_ban(adresse: str) -> dict[str, Any]:
    """Géocodage via l'API BAN (Base Adresse Nationale - France)."""
    url = "https://api-adresse.data.gouv.fr/search/"
    params = {"q": adresse, "limit": 1}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

        if data.get("features"):
            feature = data["features"][0]
            coords = feature["geometry"]["coordinates"]
            props = feature["properties"]
            return {
                "lat": coords[1],
                "lng": coords[0],
                "adresse_complete": props.get("label", adresse),
                "code_insee": props.get("citycode", ""),
                "code_postal": props.get("postcode", ""),
                "ville": props.get("city", ""),
                "provider": "ban",
                "score": props.get("score", 0),
            }

        logger.warning(f"Adresse non trouvée : {adresse}")
        return {"lat": 0, "lng": 0, "adresse_complete": adresse, "provider": "ban", "error": "not_found"}

    except Exception as e:
        logger.error(f"Erreur géocodage BAN : {e}")
        return {"lat": 0, "lng": 0, "adresse_complete": adresse, "provider": "ban", "error": str(e)}


async def _geocoder_osm(adresse: str) -> dict[str, Any]:
    """Géocodage via OpenStreetMap Nominatim."""
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": adresse, "format": "json", "limit": 1, "countrycodes": "fr"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=10, headers={
                "User-Agent": "TyphoonApp/1.0 (risk-assessment)",
            })
            response.raise_for_status()
            data = response.json()

        if data:
            return {
                "lat": float(data[0]["lat"]),
                "lng": float(data[0]["lon"]),
                "adresse_complete": data[0].get("display_name", adresse),
                "provider": "openstreetmap",
            }

        return {"lat": 0, "lng": 0, "adresse_complete": adresse, "provider": "openstreetmap", "error": "not_found"}

    except Exception as e:
        logger.error(f"Erreur géocodage OSM : {e}")
        return {"lat": 0, "lng": 0, "adresse_complete": adresse, "provider": "openstreetmap", "error": str(e)}
