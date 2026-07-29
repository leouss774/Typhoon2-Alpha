from __future__ import annotations

import httpx

from app.core.config import settings


async def fetch_climate(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": "2041-01-01",
        "end_date": "2050-12-31",
        "models": "EC_Earth3P_HR,MRI_AGCM3_2_S",
        "daily": "temperature_2m_max,precipitation_sum",
    }
    resp = await client.get(settings.open_meteo_climate_url, params=params)
    resp.raise_for_status()
    return resp.json()
