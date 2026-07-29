from __future__ import annotations

import httpx

from app.core.config import settings


async def fetch_rga_v2(client: httpx.AsyncClient, lat: float, lon: float) -> dict | None:
    if not settings.georisques_v2_enabled or not settings.georisques_v2_token:
        return None
    try:
        resp = await client.get(
            f"{settings.georisques_v2_base_url}/rga",
            params={"longitude": str(lon), "latitude": str(lat)},
            headers={"Authorization": f"Bearer {settings.georisques_v2_token}"},
        )
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None
