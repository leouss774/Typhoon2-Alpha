"""Risques naturels et technologiques via l'API Georisques v1 (BRGM).

Doc : https://www.georisques.gouv.fr/doc-api
Public, gratuit, sans clé (v1).
"""

from __future__ import annotations

import httpx

from app.core.config import settings

_BASE = settings.georisques_base_url


async def _get(client: httpx.AsyncClient, path: str, params: dict) -> dict | list | None:
    response = await client.get(f"{_BASE}/{path}", params=params)
    response.raise_for_status()
    return response.json()


async def fetch_georisques(
    client: httpx.AsyncClient, citycode: str, lat: float, lon: float, rayon_m: int = 1000
) -> dict:
    """Interroge les endpoints Georisques pertinents."""
    resultat: dict = {"erreurs": []}
    latlon = f"{lon},{lat}"

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
            resultat[cle] = await _get(client, path, params)
        except httpx.HTTPError as exc:
            resultat[cle] = None
            resultat["erreurs"].append({"source": f"georisques.{cle}", "erreur": str(exc)})

    resultat["lien_rapport_pdf"] = f"{_BASE}/rapport_pdf?latlon={latlon}"
    return resultat
