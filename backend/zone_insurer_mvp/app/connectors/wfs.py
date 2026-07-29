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
    return coord[0], coord[1]


def _iter_coords(geometry: dict):
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
    resp = await client.get(
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
    resp.raise_for_status()
    return resp.json().get("features", [])


async def fetch_distances(client: httpx.AsyncClient, lat: float, lon: float, search_radius_m: float = 2000.0) -> dict:
    water_features = await _wfs_get_features(client, "BDTOPO_V3:troncon_hydrographique", lat, lon, search_radius_m)
    if not water_features:
        water_features = await _wfs_get_features(client, "BDTOPO_V3:surface_hydrographique", lat, lon, search_radius_m)
    forest_features = await _wfs_get_features(client, "IGNF_MASQUE-FORET.2021-2023:masque_foret", lat, lon, search_radius_m)
    return {
        "distance_cours_eau_m": _min_distance_to_features(lat, lon, water_features),
        "distance_foret_m": _min_distance_to_features(lat, lon, forest_features),
    }
