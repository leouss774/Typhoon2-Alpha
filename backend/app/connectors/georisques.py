"""
Risques naturels et technologiques via l'API Georisques v1 (BRGM / Ministere
de la Transition Ecologique).

Doc interactive (Swagger, App JS) : https://www.georisques.gouv.fr/doc-api
Public, gratuit, sans cle (v1). Limite : 1000 requetes/min/IP.
Base URL : https://www.georisques.gouv.fr/api/v1

IMPORTANT - fiabilite des routes ci-dessous :
Confirmees par un test reel (adresse a Bourgueil, 37) : gaspar/risques,
gaspar/catnat, cavites, zonage_sismique, radon et mvt renvoient bien du
201/200 avec les parametres utilises ici. Seule "azi" (atlas des zones
inondables) a renvoye une 404 avec le couple de parametres (latlon+rayon)
utilise par les autres routes "point" (mvt, cavites) : par analogie avec
zonage_sismique/radon (qui fonctionnent avec code_insee seul), ce module
tente maintenant code_insee seul pour azi. C'est un ajustement raisonne,
pas une certitude : si ca 404 encore, verifiez le Swagger interactif
(https://www.georisques.gouv.fr/doc-api) pour le bon nom/parametre de
cette route et signalez-le pour correction.
Chaque appel reste isole dans son propre try/except : si une route a
change, le reste du diagnostic continue de fonctionner et l'erreur est
remontee dans la cle "erreurs" du resultat plutot que de faire planter
le script.
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
    """Interroge les endpoints Georisques pertinents pour le diagnostic Typhoon.

    Retourne un dict avec une cle par sous-source, plus une cle "erreurs"
    listant les sous-sources qui ont echoue (ex. route renommee, service
    indisponible) sans jamais lever d'exception.
    """
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

    # Le rapport PDF n'est pas telecharge ici (fichier binaire) : on fournit
    # juste le lien direct, exploitable par le frontend ou en piece jointe.
    resultat["lien_rapport_pdf"] = f"{_BASE}/rapport_pdf?latlon={latlon}"

    return resultat
