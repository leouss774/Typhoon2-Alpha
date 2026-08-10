"""Routes de geocodage exposees au frontend.

Couvrent la carte single-adresse et le module "exploration de zone"
(`frontend/jumeau_numerique/index.html`) :
  - GET /api/geocode          -> meilleur resultat pour une adresse/ville
  - GET /api/geocode/search   -> autocompletion de communes (suggestions)

Le connecteur sous-jacent (app.connectors.geocoding) utilise la Geoplateforme
IGN (data.geopf.fr/geocodage/search), successeur de l'API Adresse,
decommissionnee fin janvier 2026.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException

from app.connectors.geocoding import (
    GeocodingError,
    geocode_address,
    search_municipalities,
)

router = APIRouter()


@router.get("/geocode")
async def geocode(q: str) -> dict:
    """Geocode une adresse/ville en un point unique (lat/lon + code INSEE)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            result = await geocode_address(client, q)
        except GeocodingError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Geocodage indisponible: {exc}") from exc

    return {
        "lat": result.lat,
        "lon": result.lon,
        "label": result.label,
        "citycode": result.citycode,
        "postcode": result.postcode,
        "city": result.city,
        "score": result.score,
    }


@router.get("/geocode/search")
async def geocode_search(q: str, limit: int = 6) -> dict:
    """Autocompletion de communes (suggestions pour l'input de la carte zone)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            results = await search_municipalities(client, q, limit=max(1, min(limit, 10)))
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Geocodage indisponible: {exc}") from exc

    return {"results": results}
