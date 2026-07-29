from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class BuildingCandidate:
    address_label: str | None
    lat: float
    lon: float


async def fetch_buildings_in_radius(client: httpx.AsyncClient, lat: float, lon: float, radius_m: float, max_buildings: int = 60) -> list[BuildingCandidate]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-6)
    bbox = f"{lon - dlon},{lat - dlat},{lon + dlon},{lat + dlat}"
    resp = await client.get(
        f"{settings.bdnb_base_url}/v1/batiments/",
        params={
            "bbox": bbox,
            "format": "geojson",
            "limit": max_buildings,
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    features = data.get("features") or []
    candidates = []
    for feat in features:
        coords = feat["geometry"]["coordinates"]
        props = feat.get("properties") or {}
        candidates.append(BuildingCandidate(
            address_label=props.get("adresse") or props.get("label"),
            lat=coords[1],
            lon=coords[0],
        ))
    return candidates


def grid_fallback_points(lat: float, lon: float, radius_m: float, spacing_m: float = 50.0, max_points: int = 60) -> list[BuildingCandidate]:
    dlat = spacing_m / 111_320.0
    dlon = spacing_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-6)
    radius_deg_lat = radius_m / 111_320.0
    radius_deg_lon = radius_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-6)
    candidates = []
    x = -radius_deg_lon
    while x <= radius_deg_lon and len(candidates) < max_points:
        y = -radius_deg_lat
        while y <= radius_deg_lat and len(candidates) < max_points:
            candidates.append(BuildingCandidate(address_label=None, lat=lat + y, lon=lon + x))
            y += dlat
        x += dlon
    return candidates
