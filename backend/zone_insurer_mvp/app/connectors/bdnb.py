from __future__ import annotations

import httpx

from app.core.config import settings


class BdnbAdresseIntrouvable(RuntimeError):
    pass


async def _geocode_bdnb(client: httpx.AsyncClient, address: str) -> str:
    resp = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/geocodage",
        params={"q": address},
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("results") or data.get("features") or [data]
    else:
        results = []
    if not results:
        raise BdnbAdresseIntrouvable(f"Geocodeur BDNB : aucun resultat pour {address!r}")
    best = results[0]
    properties = best.get("properties") if isinstance(best.get("properties"), dict) else {}
    cle_interop_adr = (
        best.get("id")
        or best.get("cle_interop_adr")
        or properties.get("id")
        or properties.get("cle_interop_adr")
    )
    if not cle_interop_adr:
        raise BdnbAdresseIntrouvable(f"Champ 'id' absent de la reponse BDNB : {best!r}")
    return cle_interop_adr


async def fetch_bdnb(client: httpx.AsyncClient, address: str) -> dict | None:
    cle_interop_adr = await _geocode_bdnb(client, address)
    resp = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/donnees/batiment_groupe_complet/adresse",
        params={"cle_interop_adr": f"eq.{cle_interop_adr}"},
    )
    resp.raise_for_status()
    rows = resp.json()
    if not rows:
        return None
    return {
        "cle_interop_adr": cle_interop_adr,
        "batiment": rows[0],
        "autres_batiments_meme_adresse": rows[1:] if len(rows) > 1 else [],
    }
