"""
Caracteristiques physiques du bati via la BDNB (Base de Donnees Nationale
des Batiments) : geometrie, materiaux de structure/toiture, annee de
construction, etc.

Procedure en 2 appels (confirmee via usage reel de l'API, cf.
docs/GUIDE_ORCHESTRATEUR_API.md) :

  1. Geocodeur propre a BDNB (different du geocodeur BAN utilise ailleurs
     dans ce projet) :
       GET https://api.bdnb.io/v1/bdnb/geocodage?q={adresse}
     -> le champ "id" de la meilleure correspondance est la
        "cle_interop_adr" (cle d'interoperabilite adresse), de la forme
        "37031_xxxx_00026" (code INSEE commune + identifiant de voie +
        numero).

  2. Donnees du/des groupe(s) de batiments a cette adresse EXACTE :
       GET https://api.bdnb.io/v1/bdnb/donnees/batiment_groupe_complet/adresse
           ?cle_interop_adr=eq.{id}
     -> renvoie directement les groupes de batiments a cette adresse
        precise. Plus besoin de deviner le batiment le plus proche dans
        toute la commune (approche abandonnee).

L'offre "Open" de BDNB ne necessite aucune cle API pour ces deux appels
(confirme par un test reel : les deux requetes fonctionnent sans en-tete
Authorization). Si BDNB_API_KEY est renseignee dans .env (ex. pour
beneficier d'un quota plus eleve), elle est ajoutee automatiquement ;
sinon les appels partent sans en-tete, sans bloquer le diagnostic.
Aucune donnee n'est simulee ici : si l'adresse n'est pas trouvee par le
geocodeur BDNB, une exception explicite est levee et remontee comme
source en erreur par collector_agent, plutot que de renvoyer un resultat
invente.
"""

from __future__ import annotations

import httpx

from app.core.config import settings


class BdnbAdresseIntrouvable(RuntimeError):
    pass


def _headers() -> dict:
    if settings.bdnb_api_key:
        return {"Authorization": f"Bearer {settings.bdnb_api_key}"}
    return {}


async def _geocode_bdnb(client: httpx.AsyncClient, address: str) -> str:
    """Etape 1 : geocodeur BDNB -> cle_interop_adr de la meilleure correspondance."""
    response = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/geocodage",
        params={"q": address},
        headers=_headers(),
    )
    response.raise_for_status()
    data = response.json()

    # La forme exacte (liste brute, ou objet avec "results"/"features") peut
    # varier selon la version de l'API : on gere les variantes plausibles
    # plutot que de supposer un seul format et de planter dessus.
    if isinstance(data, list):
        results = data
    elif isinstance(data, dict):
        results = data.get("results") or data.get("features") or [data]
    else:
        results = []

    if not results:
        raise BdnbAdresseIntrouvable(f"Geocodeur BDNB : aucun resultat pour {address!r}")

    best = results[0]
    properties = best.get("properties") if isinstance(best, dict) else None
    if not isinstance(properties, dict):
        properties = {}
    cle_interop_adr = best.get("id") or best.get("cle_interop_adr") or properties.get("id") or properties.get("cle_interop_adr")
    if not cle_interop_adr:
        raise BdnbAdresseIntrouvable(
            f"Geocodeur BDNB : champ 'id' absent de la reponse : {best!r}"
        )
    return cle_interop_adr


async def fetch_bdnb(client: httpx.AsyncClient, address: str) -> dict | None:
    """Retourne les donnees BDNB (geometrie, materiaux...) pour cette adresse exacte.

    Leve BdnbAdresseIntrouvable si le geocodeur BDNB ne trouve pas
    l'adresse. Retourne None (sans erreur) si l'adresse est geocodee mais
    qu'aucun batiment n'est associe a cette cle_interop_adr dans la BDNB.
    """
    cle_interop_adr = await _geocode_bdnb(client, address)

    response = await client.get(
        f"{settings.bdnb_base_url}/v1/bdnb/donnees/batiment_groupe_complet/adresse",
        params={"cle_interop_adr": f"eq.{cle_interop_adr}"},
        headers=_headers(),
    )
    response.raise_for_status()
    rows = response.json()

    if not rows:
        return None

    return {
        "cle_interop_adr": cle_interop_adr,
        "batiment": rows[0],
        "autres_batiments_meme_adresse": rows[1:] if len(rows) > 1 else [],
    }
