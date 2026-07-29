from __future__ import annotations

from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass
class GeocodeResult:
    label: str
    lat: float
    lon: float
    citycode: str


async def geocode_address(client: httpx.AsyncClient, address: str) -> GeocodeResult:
    if "," in address:
        parts = address.split(",")
        if len(parts) == 2:
            try:
                lat, lon = float(parts[0].strip()), float(parts[1].strip())
                rev = await _reverse_geocode(client, lat, lon)
                label = rev.label if rev else address
                citycode = rev.citycode if rev else "00000"
                return GeocodeResult(label=label, lat=lat, lon=lon, citycode=citycode)
            except ValueError:
                pass
    params = {"q": address, "limit": 1}
    resp = await client.get(settings.geocoding_url, params=params)
    resp.raise_for_status()
    data = resp.json()
    feats = data.get("features") or []
    if not feats:
        raise ValueError(f"Aucun resultat pour {address}")
    f = feats[0]
    lon, lat = f["geometry"]["coordinates"]
    props = f["properties"]
    return GeocodeResult(
        label=props.get("label") or address,
        lat=lat,
        lon=lon,
        citycode=props.get("citycode") or "00000",
    )


async def _reverse_geocode(client: httpx.AsyncClient, lat: float, lon: float) -> GeocodeResult | None:
    try:
        resp = await client.get(f"{settings.geocoding_url}/reverse", params={"lon": lon, "lat": lat, "limit": 1})
        resp.raise_for_status()
        data = resp.json()
        feats = data.get("features") or []
        if feats:
            props = feats[0]["properties"]
            return GeocodeResult(
                label=props.get("label") or f"{lat},{lon}",
                lat=lat,
                lon=lon,
                citycode=props.get("citycode") or "00000",
            )
    except Exception:
        pass
    return None
