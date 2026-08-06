"""
Geocodage d'adresse -> coordonnees + code INSEE commune.

Source : API Geocodage de la Geoplateforme IGN (successeur de l'ancienne
API Adresse api-adresse.data.gouv.fr, decommissionnee fin janvier 2026).
Publique, gratuite, sans cle. Limite : 50 appels/seconde/IP.

Doc : https://data.geopf.fr/geocodage/search
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class GeocodeResult:
    label: str  # adresse normalisee retournee par le geocodeur
    citycode: str  # code INSEE de la commune (utilise par BDNB/Georisques)
    postcode: str
    city: str
    score: float  # confiance du geocodage (0-1)
    lat: float
    lon: float


class GeocodingError(RuntimeError):
    pass


async def reverse_geocode(client: httpx.AsyncClient, lat: float, lon: float) -> GeocodeResult:
    """Reverse geocode des coordonnees -> code INSEE + infos commune.

    Utilise l'API reverse de la Geoplateforme IGN :
    https://data.geopf.fr/geocodage/reverse?lon={lon}&lat={lat}

    Leve GeocodingError si les coordonnees ne peuvent pas etre resolues.
    """
    response = await client.get(
        # URL reverse dérivée de l'URL de geocodage direct
        settings.geocoding_url.replace("/search", "/reverse"),
        params={"lon": lon, "lat": lat},
    )
    response.raise_for_status()
    data = response.json()

    features = data.get("features") or []
    if not features:
        raise GeocodingError(f"Aucun resultat de reverse geocodage pour {lat},{lon}")

    feature = features[0]
    props = feature.get("properties", {})
    citycode = props.get("citycode") or ""

    return GeocodeResult(
        label=props.get("label", f"{lat:.5f},{lon:.5f}"),
        citycode=citycode,
        postcode=props.get("postcode", ""),
        city=props.get("city", ""),
        score=props.get("score", 0.5),
        lat=lat,
        lon=lon,
    )


async def geocode_address(client: httpx.AsyncClient, address: str) -> GeocodeResult:
    """Geocode une adresse texte en coordonnees + code INSEE.

    Leve GeocodingError si l'adresse ne peut pas etre resolue (aucun
    resultat retourne par le service).
    """
    response = await client.get(
        settings.geocoding_url,
        params={"q": address, "limit": 1},
    )
    response.raise_for_status()
    data = response.json()

    features = data.get("features") or []
    if not features:
        raise GeocodingError(f"Aucun resultat de geocodage pour l'adresse : {address!r}")

    feature = features[0]
    properties = feature["properties"]
    lon, lat = feature["geometry"]["coordinates"]

    return GeocodeResult(
        label=properties.get("label", address),
        citycode=properties["citycode"],
        postcode=properties.get("postcode", ""),
        city=properties.get("city", ""),
        score=properties.get("score", 0.0),
        lat=lat,
        lon=lon,
    )


async def search_municipalities(
    client: httpx.AsyncClient, q: str, limit: int = 6
) -> list[dict]:
    """Recherche de communes (autocompletion) via la Geoplateforme IGN.

    Complement de `geocode_address` : retourne une liste de suggestions
    municipales pour l'autocomplete du frontend (le geocodage simple ne
    renvoie qu'un seul meilleur resultat, sans liste).

    Retour : [{label, city, context, citycode, postcode, score, lat, lon}, ...]
    (meme forme que l'ancienne API Adresse, decommissionnee fin 01/2026).
    """
    response = await client.get(
        settings.geocoding_url,
        params={"q": q, "type": "municipality", "limit": limit},
    )
    response.raise_for_status()
    data = response.json()

    suggestions = []
    for feature in data.get("features") or []:
        props = feature.get("properties", {})
        coords = feature.get("geometry", {}).get("coordinates") or [None, None]
        suggestions.append({
            "label": props.get("label", ""),
            "city": props.get("city") or props.get("name", ""),
            "context": props.get("context", ""),
            "citycode": props.get("citycode", ""),
            "postcode": props.get("postcode", ""),
            "score": props.get("score"),
            "lat": coords[1],
            "lon": coords[0],
        })
    return suggestions
