from __future__ import annotations

import httpx

from app.core.config import settings

_BASE = settings.georisques_base_url


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict | list | None:
    resp = await client.get(f"{_BASE}/{path}", params=params)
    resp.raise_for_status()
    return resp.json()


async def fetch_georisques(client: httpx.AsyncClient, citycode: str, lat: float, lon: float, rayon_m: int = 1000) -> dict:
    latlon = f"{lon},{lat}"
    result: dict = {"erreurs": []}
    sources = {
        "risques_commune": ("gaspar/risques", {"code_insee": citycode, "rayon": rayon_m}),
        "catnat": ("gaspar/catnat", {"code_insee": citycode, "rayon": rayon_m}),
        "zones_inondables": ("azi", {"code_insee": citycode}),
        "cavites": ("cavites", {"latlon": latlon, "rayon": rayon_m}),
        "zonage_sismique": ("zonage_sismique", {"code_insee": citycode}),
        "radon": ("radon", {"code_insee": citycode}),
        "mouvements_de_terrain": ("mvt", {"latlon": latlon, "rayon": rayon_m}),
    }
    for cle, (path, params) in sources.items():
        try:
            result[cle] = await _get(client, path, params)
        except httpx.HTTPError as exc:
            result[cle] = None
            result["erreurs"].append({"source": f"georisques.{cle}", "erreur": str(exc)})
    return result
