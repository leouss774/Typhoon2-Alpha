"""Geocodage via la BAN (Base Adresse Nationale) — Géoplateforme IGN.

API publique, sans clé.
https://data.geopf.fr/geocodage/search

Chaîne d'appels réels (pas de fallback fabrication) :
  1. IGN Géoplateforme avec type=housenumber
  2. IGN Géoplateforme sans filtre de type
  3. BAN data.gouv.fr (API officielle)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── API BAN data.gouv.fr (fallback réel) ──────────────────────────────────────
_BAN_URL = "https://api-adresse.data.gouv.fr/search/"


@dataclass
class GeoResult:
    label: str
    citycode: str
    postcode: str
    city: str
    lat: float
    lon: float
    score: float


async def _call_api(client: httpx.AsyncClient, url: str, params: dict) -> dict | None:
    """Appelle une API de géocodage et retourne les données ou None."""
    try:
        response = await client.get(url, params=params, timeout=8)
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        logger.warning("geocoding -- API %s échouée: %s", url, exc)
        return None


def _features_to_result(features: list, address: str) -> GeoResult | None:
    """Extrait le premier résultat d'une réponse API."""
    if not features:
        return None
    props = features[0].get("properties", {})
    coords = features[0].get("geometry", {}).get("coordinates", [0, 0])
    return GeoResult(
        label=props.get("label", address),
        citycode=props.get("citycode", ""),
        postcode=props.get("postcode", ""),
        city=props.get("city", ""),
        lat=coords[1] if len(coords) > 1 else 0,
        lon=coords[0] if len(coords) > 0 else 0,
        score=props.get("score", 0.0),
    )


def _empty_result(address: str, score: float = 0.0) -> GeoResult:
    """Retourne un GeoResult vide (aucune donnée fabriquée)."""
    return GeoResult(
        label=address,
        citycode="",
        postcode="",
        city="",
        lat=0.0,
        lon=0.0,
        score=score,
    )


async def geocode_address(client: httpx.AsyncClient, address: str) -> GeoResult:
    """Geocode une adresse texte via des API réelles uniquement.

    Chaîne (1 → 2 → 3) :
      1. IGN Géoplateforme avec type=housenumber (précision max)
      2. IGN Géoplateforme sans filtre        (recherche élargie)
      3. BAN data.gouv.fr                      (API officielle complémentaire)

    Si aucune API ne trouve l'adresse, retourne un GeoResult vide avec score=0.0.
    Jamais de ValueError, jamais de données fabriquées.
    """
    # ── 1. IGN Géoplateforme avec type=housenumber ──────────────────────────
    data = await _call_api(
        client,
        settings.geocoding_url,
        {"q": address, "limit": 1, "type": "housenumber"},
    )
    result = _features_to_result(data.get("features", []) if data else [], address) if data else None
    if result:
        logger.info("  -> IGN housenumber: %s (score=%.2f)", result.label, result.score)
        return result

    # ── 2. IGN Géoplateforme sans type (recherche élargie) ──────────────────
    logger.info("geocoding -- fallback 1: IGN sans filtre type pour %r", address)
    data = await _call_api(client, settings.geocoding_url, {"q": address, "limit": 1})
    result = _features_to_result(data.get("features", []) if data else [], address) if data else None
    if result:
        logger.info("  -> IGN sans filtre: %s (score=%.2f)", result.label, result.score)
        return result

    # ── 3. BAN data.gouv.fr (API officielle) ────────────────────────────────
    logger.info("geocoding -- fallback 2: BAN data.gouv.fr pour %r", address)
    data = await _call_api(client, _BAN_URL, {"q": address, "limit": 1})
    result = _features_to_result(data.get("features", []) if data else [], address) if data else None
    if result:
        logger.info("  -> BAN: %s (score=%.2f)", result.label, result.score)
        return result

    # ── Aucune API n'a trouvé l'adresse → résultat vide, score faible ────────
    logger.warning("geocoding -- aucune API n'a trouvé %r (score=0.0)", address)
    return _empty_result(address)


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
        logger.warning("reverse_geocode -- introuvable pour %s,%s", lat, lon)
        return _empty_result(f"{lat:.5f},{lon:.5f}")

    props = features[0].get("properties", {})
    coords = features[0].get("geometry", {}).get("coordinates", [0, 0])

    return GeoResult(
        label=props.get("label", f"{lat:.5f},{lon:.5f}"),
        citycode=props.get("citycode", ""),
        postcode=props.get("postcode", ""),
        city=props.get("city", ""),
        lat=coords[1] if len(coords) > 1 else lat,
        lon=coords[0] if len(coords) else lon,
        score=props.get("score", 0.0),
    )
