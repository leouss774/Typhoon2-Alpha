"""Geocodage via la BAN (Base Adresse Nationale) — Géoplateforme IGN.

API publique, sans clé.
https://data.geopf.fr/geocodage/search
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class GeoResult:
    label: str
    citycode: str
    postcode: str
    city: str
    lat: float
    lon: float
    score: float


async def geocode_address(client: httpx.AsyncClient, address: str) -> GeoResult:
    """Geocode une adresse texte via la BAN."""
    response = await client.get(
        settings.geocoding_url,
        params={"q": address, "limit": 1, "type": "housenumber"},
    )
    response.raise_for_status()
    data = response.json()

    features = data.get("features", [])
    if not features:
        raise ValueError(f"Adresse introuvable : {address!r}")

    props = features[0].get("properties", {})
    coords = features[0].get("geometry", {}).get("coordinates", [0, 0])

    return GeoResult(
        label=props.get("label", address),
        citycode=props.get("citycode", ""),
        postcode=props.get("postcode", ""),
        city=props.get("city", ""),
        lat=coords[1] if len(coords) > 1 else 0,
        lon=coords[0] if coords else 0,
        score=props.get("score", 0.0),
    )


async def reverse_geocode(client: httpx.AsyncClient, lat: float, lon: float) -> GeoResult:
    """Reverse geocode à partir de coordonnées."""
    response = await client.get(
        settings.geocoding_url,
        params={"lat": lat, "lon": lon, "limit": 1},
    )
    response.raise_for_status()
    data = response.json()

    features = data.get("features", [])
    if not features:
        raise ValueError(f"Reverse geocode introuvable pour {lat},{lon}")

    props = features[0].get("properties", {})
    coords = features[0].get("geometry", {}).get("coordinates", [0, 0])

    return GeoResult(
        label=props.get("label", f"{lat:.5f},{lon:.5f}"),
        citycode=props.get("citycode", ""),
        postcode=props.get("postcode", ""),
        city=props.get("city", ""),
        lat=coords[1] if len(coords) > 1 else lat,
        lon=coords[0] if coords else lon,
        score=props.get("score", 0.0),
    )
