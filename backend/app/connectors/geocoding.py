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
