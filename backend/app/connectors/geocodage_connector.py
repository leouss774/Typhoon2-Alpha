from __future__ import annotations
from dataclasses import dataclass
import httpx

BASE_URL = "https://api-adresse.data.gouv.fr/search/"

class AdresseNonTrouveeError(Exception):
    def __init__(self, adresse: str):
        super().__init__(f"Adresse non trouvée : {adresse}")
        self.adresse = adresse

@dataclass
class GeocodageResult:
    lat: float
    lon: float
    label: str
    code_insee: str
    score: float

async def geocoder_adresse(adresse: str) -> GeocodageResult:
    """
    API Adresse Base Adresse Nationale (BAN) — Etalab, gratuite, sans clé.
    Aucun fallback si non trouvé : erreur explicite renvoyée au front.
    """
    async with httpx.AsyncClient(timeout=5.0) as client:
        r = await client.get(BASE_URL, params={"q": adresse, "limit": 1})
        r.raise_for_status()
        data = r.json()
        if not data.get("features"):
            raise AdresseNonTrouveeError(adresse)
        feat = data["features"][0]
        lon, lat = feat["geometry"]["coordinates"]
        props = feat["properties"]
        return GeocodageResult(
            lat=lat,
            lon=lon,
            label=props["label"],
            code_insee=props.get("citycode") or "",
            score=props.get("score") or 0.0
        )
