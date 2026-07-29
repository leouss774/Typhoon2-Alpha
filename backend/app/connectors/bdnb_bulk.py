"""
bdnb_bulk — enumerate buildings inside a radius around a center point
using the BDNB batiment_groupe_complet endpoint with bbox filter.

Falls back to grid sampling if the bulk query fails or returns empty.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import httpx

from app.core.config import settings

BDNB_BASE_URL = getattr(settings, "bdnb_base_url", "https://api.bdnb.io")


@dataclass
class BuildingCandidate:
    cle_interop_adr: str | None
    address_label: str | None
    lat: float
    lon: float


def _bbox_from_radius(lat: float, lon: float, radius_m: float) -> tuple[float, float, float, float]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-6)
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


async def fetch_buildings_in_radius(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    radius_m: float,
    max_buildings: int,
) -> list[BuildingCandidate]:
    lon_min, lat_min, lon_max, lat_max = _bbox_from_radius(lat, lon, radius_m)
    response = await client.get(
        f"{BDNB_BASE_URL}/v1/bdnb/donnees/batiment_groupe_complet",
        params={
            "bbox": f"{lon_min},{lat_min},{lon_max},{lat_max}",
            "limit": max_buildings,
        },
    )
    response.raise_for_status()
    data = response.json()
    rows = data if isinstance(data, list) else data.get("results", data.get("items", []))

    candidates: list[BuildingCandidate] = []
    for row in rows[:max_buildings]:
        geom = row.get("geom_groupe") or row.get("geometry") or {}
        coords = geom.get("coordinates")
        b_lat, b_lon = (coords[1], coords[0]) if coords else (lat, lon)
        candidates.append(
            BuildingCandidate(
                cle_interop_adr=row.get("cle_interop_adr"),
                address_label=row.get("libelle_adr_principale_ban") or row.get("adresse"),
                lat=b_lat,
                lon=b_lon,
            )
        )
    return candidates


def grid_fallback_points(
    lat: float, lon: float, radius_m: float, spacing_m: float, max_points: int
) -> list[BuildingCandidate]:
    dlat = spacing_m / 111_320.0
    dlon = spacing_m / (111_320.0 * math.cos(math.radians(lat)) or 1e-6)
    steps = max(1, int(radius_m / spacing_m))

    points: list[BuildingCandidate] = []
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            p_lat = lat + i * dlat
            p_lon = lon + j * dlon
            dist_m = math.hypot(i * spacing_m, j * spacing_m)
            if dist_m <= radius_m:
                points.append(BuildingCandidate(cle_interop_adr=None, address_label=None, lat=p_lat, lon=p_lon))
            if len(points) >= max_points:
                return points
    return points
