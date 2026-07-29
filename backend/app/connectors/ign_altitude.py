"""
Altimetrie IGN (Geoplateforme) : altitude d'un point.

Utile pour affiner l'exposition au risque d'inondation (un terrain en
contrebas est plus expose qu'un terrain en hauteur, a aleas identiques).

Doc : https://geoplateforme.pages.gpf-tech.ign.fr/altimetrie/api-rest-calcul-altimetrique/
Public, gratuit, sans cle. Limite : 5 requetes/seconde/IP.

Note d'implementation : le nom exact de la "resource" a utiliser (le jeu de
donnees altimetrique interroge, ex. RGE ALTI) peut evoluer. Plutot que de le
coder en dur, ce module l'auto-decouvre au premier appel via la route
/1.0/resources/ et le met en cache pour les appels suivants.
"""

from __future__ import annotations

import httpx

from app.core.config import settings

_cached_resource_id: str | None = None

# Valeur de repli si l'auto-decouverte echoue (ex. API resources indisponible).
_FALLBACK_RESOURCE_ID = "ign_rge_alti_wld"


async def _discover_altitude_resource(client: httpx.AsyncClient) -> str:
    global _cached_resource_id
    if _cached_resource_id:
        return _cached_resource_id

    try:
        response = await client.get(
            f"{settings.ign_altitude_base_url}/resources/",
            params={"keywords": "ALTI"},
        )
        response.raise_for_status()
        data = response.json()
        resources = data.get("resources") or []
        if resources:
            _cached_resource_id = resources[0]["_id"]
            return _cached_resource_id
    except (httpx.HTTPError, KeyError, ValueError):
        pass

    _cached_resource_id = _FALLBACK_RESOURCE_ID
    return _cached_resource_id


async def fetch_altitude(client: httpx.AsyncClient, lat: float, lon: float) -> float | None:
    """Retourne l'altitude (en metres) au point donne, ou None si indisponible."""
    resource = await _discover_altitude_resource(client)

    response = await client.get(
        f"{settings.ign_altitude_base_url}/calcul/alti/rest/elevation.json",
        params={"lon": lon, "lat": lat, "resource": resource, "zonly": "true"},
    )
    response.raise_for_status()
    data = response.json()

    elevations = data.get("elevations") or []
    if not elevations:
        return None

    value = elevations[0]
    # Selon les parametres, l'API renvoie soit un nombre brut (zonly=true),
    # soit un objet {"z": ...} (zonly=false).
    if isinstance(value, dict):
        value = value.get("z")

    if value is None or value == -99999:
        # -99999 = zone non couverte par la ressource altimetrique.
        return None
    return float(value)
