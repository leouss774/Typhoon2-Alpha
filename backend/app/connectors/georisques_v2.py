"""
Georisques v2 — RGA (retrait-gonflement des argiles), authentifie.

Complementaire de connectors/georisques.py (v1, public, sans cle) : la v2
expose un alea RGA plus fin (et des infos commune associees) mais exige un
jeton (GEORISQUES_V2_TOKEN dans backend/.env). Desactive par defaut
(settings.georisques_v2_enabled) pour ne rien casser sur un poste qui n'a
pas encore ce jeton.

STATUS: cette route (api/v2/rga) n'a pas pu etre testee en conditions
reelles dans mon environnement (reseau sandbox sans acces a
georisques.gouv.fr) — verifiez le premier appel reel avant de faire
confiance a la forme exacte de la reponse. Comme pour georisques.py v1,
chaque appel reste isole : un echec remonte dans "erreurs", ne fait jamais
planter le reste du diagnostic.
"""

from __future__ import annotations

import httpx

from app.core.config import settings


class GeorisquesV2NonConfigure(RuntimeError):
    pass


async def fetch_rga_v2(client: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """Interroge Georisques v2 /rga pour un point donne.

    Leve GeorisquesV2NonConfigure si desactive ou sans jeton — a intercepter
    la ou cette fonction est appelee (meme pattern que Copernicus/DVF dans
    collector_agent.py : une source volontairement coupee n'est pas une
    erreur, juste une valeur None).
    """
    if not settings.georisques_v2_enabled:
        raise GeorisquesV2NonConfigure("georisques_v2_enabled=False")
    if not settings.georisques_v2_token:
        raise GeorisquesV2NonConfigure(
            "GEORISQUES_V2_TOKEN manquant. Renseigne-le dans backend/.env "
            "(voir backend/.env.example) et passe georisques_v2_enabled a True."
        )

    response = await client.get(
        f"{settings.georisques_v2_base_url}/rga",
        params={"longitude": str(lon), "latitude": str(lat)},
        headers={"Authorization": f"Bearer {settings.georisques_v2_token}"},
    )
    response.raise_for_status()
    return response.json()
