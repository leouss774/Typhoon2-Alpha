"""
IGN WFS (Geoplateforme) — distance au cours d'eau et a la foret les plus
proches.

Deux couches interrogees (BD TOPO V3 / occupation du sol) :
  - BDTOPO_V3:troncon_hydrographique (+ surface_hydrographique) : reseau
    hydrographique -> distance de reference pour affiner l'exposition
    inondation au-dela de l'alea communal Georisques.
  - IGNF_MASQUE-FORET.2021-2023:masque_foret : emprise forestiere -> proxy
    de proximite pour le risque feu de foret (a defaut d'un aléa "feu de
    foret" geolocalise plus precis que la donnee communale de Georisques).

STATUS: non teste en conditions reelles (reseau sandbox sans acces a
data.geopf.fr). L'approximation de distance (au sommet de geometrie le
plus proche, pas au segment le plus proche) est volontairement simple —
pas de dependance shapely, coherent avec le choix deja fait dans
app/digital_twin/geometry_builder.py. Suffisant pour classer "proche /
moyen / loin", pas pour un calcul geometrique de precision.
"""

from __future__ import annotations

import math

import httpx

from app.core.config import settings


def _bbox_around(lat: float, lon: float, radius_m: float) -> str:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-6)
    return f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat},EPSG:4326"


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _to_lonlat(coord: list) -> tuple[float, float]:
    """Extract (lon, lat) from a 2D or 3D coordinate tuple."""
    return coord[0], coord[1]


def _iter_coords(geometry: dict):
    """Yield every (lon, lat) vertex in a GeoJSON geometry, whatever its type."""
    coords = geometry.get("coordinates")
    gtype = geometry.get("type")
    if gtype == "Point":
        yield _to_lonlat(coords)
    elif gtype in ("MultiPoint", "LineString"):
        for c in coords:
            yield _to_lonlat(c)
    elif gtype in ("MultiLineString", "Polygon"):
        for ring in coords:
            for c in ring:
                yield _to_lonlat(c)
    elif gtype == "MultiPolygon":
        for polygon in coords:
            for ring in polygon:
                for c in ring:
                    yield _to_lonlat(c)


def _min_distance_to_features(lat: float, lon: float, features: list[dict]) -> float | None:
    best: float | None = None
    for feature in features:
        geometry = feature.get("geometry")
        if not geometry:
            continue
        for vertex_lon, vertex_lat in _iter_coords(geometry):
            d = _haversine_m(lat, lon, vertex_lat, vertex_lon)
            if best is None or d < best:
                best = d
    return best


async def _wfs_get_features(client: httpx.AsyncClient, type_name: str, lat: float, lon: float, search_radius_m: float) -> list[dict]:
    response = await client.get(
        settings.wfs_base_url,
        params={
            "service": "WFS",
            "version": "2.0.0",
            "request": "GetFeature",
            "typeNames": type_name,
            "outputFormat": "application/json",
            "bbox": _bbox_around(lat, lon, search_radius_m),
            "count": 50,
        },
    )
    response.raise_for_status()
    data = response.json()
    return data.get("features", [])


async def fetch_distance_to_waterway(client: httpx.AsyncClient, lat: float, lon: float, search_radius_m: float = 2000.0) -> float | None:
    """Distance approx. (m) au cours d'eau le plus proche, ou None si aucun
    trouve dans le rayon de recherche (pas forcement 'aucun risque' — peut
    juste vouloir dire 'plus loin que search_radius_m')."""
    features = await _wfs_get_features(client, "BDTOPO_V3:troncon_hydrographique", lat, lon, search_radius_m)
    if not features:
        features = await _wfs_get_features(client, "BDTOPO_V3:surface_hydrographique", lat, lon, search_radius_m)
    return _min_distance_to_features(lat, lon, features)


async def fetch_distance_to_forest(client: httpx.AsyncClient, lat: float, lon: float, search_radius_m: float = 2000.0) -> float | None:
    """Distance approx. (m) a la foret la plus proche (masque foret IGN),
    ou None si aucune trouvee dans le rayon de recherche."""
    features = await _wfs_get_features(client, "IGNF_MASQUE-FORET.2021-2023:masque_foret", lat, lon, search_radius_m)
    return _min_distance_to_features(lat, lon, features)


async def fetch_distances(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """Point d'entree combine — meme pattern que les autres connecteurs
    (une seule fonction a appeler depuis collector_agent.py)."""
    return {
        "distance_cours_eau_m": await fetch_distance_to_waterway(client, lat, lon),
        "distance_foret_m": await fetch_distance_to_forest(client, lat, lon),
    }
