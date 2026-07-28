"""
collector_agent : orchestrateur de collecte de donnees.

C'est le premier noeud du graphe LangGraph decrit dans le README
(voir "Architecture multi-agents"). Cette version est un agent "test" :
il ne depend pas encore de LangGraph, pour permettre de valider rapidement
la connectivite reelle aux sources avant de le brancher dans le
StateGraph complet (scoring_agent, rag_agent, digital_twin_agent).

Sequence :
    1. Geocodage de l'adresse -> lat/lon/citycode (bloquant, requis par
       Georisques, IGN Altitude et Copernicus). Deux formes d'entree sont
       acceptees : une adresse texte classique (geocodage direct), ou des
       coordonnees brutes "lat,lon" telles qu'envoyees par la grille
       d'echantillonnage de zone (app/scoring/zone_scoring.py), auquel cas
       on utilise le reverse geocodage pour retrouver la commune.
    2. Fan-out : BDNB, Georisques, IGN Altitude, Open-Meteo, Copernicus,
       DVF local sont interroges EN PARALLELE via asyncio.gather.
    3. Fan-in : les resultats (succes ou echecs) sont assembles dans un
       seul dict "building_data".

Aucune exception individuelle ne remonte : chaque source en echec est
consignee dans building_data["erreurs"] pour que le diagnostic reste
utilisable meme si une source est indisponible (cle API manquante, route
renommee, service en panne, jeton Copernicus non configure...). Aucune
valeur n'est simulee : une source indisponible reste "null" avec son
erreur explicite, jamais remplacee par une donnee inventee.

Note sur BDNB en mode zone : le geocodeur BDNB (etape interne a
connectors/bdnb.py) cherche une adresse postale, pas des coordonnees. Un
point de grille tombant en pleine rue, sur un terrain nu ou une parcelle
sans adresse normalisee ne trouvera donc logiquement aucun batiment
(bdnb=None, erreur consignee) : ce n'est pas un bug, juste une limite du
geocodeur BDNB lui-meme.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable
from datetime import datetime, timezone

import httpx

from app.connectors import bdnb as bdnb_connector
from app.connectors.bdnb import BdnbAdresseIntrouvable
from app.connectors import copernicus
from app.connectors import dvf_lookup
from app.connectors import georisques as georisques_connector
from app.connectors import ign_altitude
from app.connectors import open_meteo
from app.connectors.geocoding import geocode_address, reverse_geocode
from app.core.config import settings
from app.core.logging import get_logger
from app.core.paca import department_code_from_citycode, department_name, is_in_paca

logger = get_logger(__name__)

# Détecte les "adresses" en fait fournies comme coordonnées brutes "lat,lon"
# par la grille d'échantillonnage de zone (app/scoring/zone_scoring.py).
# Dans ce cas on doit reverse-geocoder (coordonnees -> commune) plutot que
# de chercher un texte libre via le geocodeur direct.
_LATLON_RE = re.compile(r"^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$")


async def _safe_call(source_name: str, coro, erreurs: list[dict]):
    """Execute un connecteur et convertit toute exception en entree d'erreur."""
    started = time.perf_counter()
    try:
        result = await coro
        logger.info("  [%s] OK (%.2fs)", source_name, time.perf_counter() - started)
        return result
    except Exception as exc:  # volontairement large : on isole chaque source
        logger.warning("  [%s] ECHEC (%.2fs) -> %s: %s", source_name, time.perf_counter() - started, type(exc).__name__, exc)
        erreurs.append({"source": source_name, "erreur": f"{type(exc).__name__}: {exc}"})
        return None


async def _fetch_bdnb_avec_repli(client: httpx.AsyncClient, address: str, label_ban: str) -> dict | None:
    """Interroge BDNB avec repli de géocodage.

    Le géocodeur BDNB (propre, différent de la BAN) est parfois plus
    fiable sur une adresse déjà normalisée (postcode/ville corrects) que
    sur le texte brut tapé par l'utilisateur — ex. un code postal
    approximatif ("06000" au lieu de "06200" pour Nice) peut suffire à
    faire échouer sa recherche interne. On tente donc d'abord le libellé
    BAN normalisé (`geocode.label`), et seulement si ça échoue on retente
    avec l'adresse brute telle que fournie, au cas où le géocodeur BDNB
    préfère au contraire la formulation originale pour ce cas précis.
    """
    try:
        return await bdnb_connector.fetch_bdnb(client, label_ban)
    except BdnbAdresseIntrouvable:
        if label_ban == address:
            raise
        logger.info("  [bdnb] libelle BAN non trouve (%r), nouvel essai avec l'adresse brute (%r)", label_ban, address)
        return await bdnb_connector.fetch_bdnb(client, address)


async def collect(address: str, enable_copernicus: bool = True, enable_dvf: bool | None = None) -> dict:
    """Point d'entree principal : lance la collecte complete pour une adresse.

    Parameters
    ----------
    address : str
        Adresse postale complete du bien.
    enable_copernicus : bool
        Si True (defaut), interroge Copernicus CDS.
        Si False, climat_copernicus sera None dans le building_data,
        sans ajouter d'erreur dans la liste des erreurs.
    enable_dvf : bool | None
        Si True, interroge le lookup DVF local (CSV par departement, a
        telecharger a la main - voir backend/data/lookup/dvf/README.md).
        Si False, dvf_local sera None sans ajouter d'erreur : pratique sur
        un poste qui n'a pas encore ces CSV, sans avoir a modifier le code
        (chaque personne peut aussi regler ca une fois pour toutes via
        DVF_ENABLED dans son .env plutot que de passer ce parametre a
        chaque appel - voir settings.dvf_enabled).
        Si None (defaut), suit settings.dvf_enabled.
    """
    if enable_dvf is None:
        enable_dvf = settings.dvf_enabled

    logger.info(
        "collector_agent -- debut collecte pour %r (enable_copernicus=%s, enable_dvf=%s)",
        address, enable_copernicus, enable_dvf,
    )
    t0 = time.perf_counter()
    erreurs: list[dict] = []

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        # Etape 1 - geocodage. Deux cas :
        #  - adresse texte classique -> geocodage direct (BAN/Geoplateforme)
        #  - "lat,lon" brut (grille d'echantillonnage de zone, cf.
        #    app/scoring/zone_scoring.py) -> reverse geocode pour retrouver
        #    la commune (citycode) exigee par Georisques/IGN/Copernicus.
        logger.info("etape 1/3 -- geocodage")
        latlon_match = _LATLON_RE.match(address)
        if latlon_match:
            lat_in, lon_in = float(latlon_match.group(1)), float(latlon_match.group(2))
            geocode = await reverse_geocode(client, lat_in, lon_in)
            logger.info(
                "  -> reverse geocode %s (citycode=%s, lat=%.5f, lon=%.5f)",
                geocode.label, geocode.citycode, geocode.lat, geocode.lon,
            )
        else:
            geocode = await geocode_address(client, address)
            logger.info(
                "  -> %s (citycode=%s, lat=%.5f, lon=%.5f, score=%.2f)",
                geocode.label, geocode.citycode, geocode.lat, geocode.lon, geocode.score,
            )

        department_code = department_code_from_citycode(geocode.citycode)

        logger.info("etape 2/3 -- collecte parallele (bdnb, georisques, ign_altitude, open_meteo, + copernicus/dvf si actives)")
        # Etape 2 - fan-out : toutes les sources live + lookups en parallele.
        # BDNB utilise son propre geocodeur interne (voir bdnb.py) : on tente
        # d'abord le libelle BAN deja normalise (plus fiable), avec repli sur
        # l'adresse brute — voir _fetch_bdnb_avec_repli ci-dessus.
        tasks: dict[str, Awaitable] = {
            "bdnb": _safe_call("bdnb", _fetch_bdnb_avec_repli(client, address, geocode.label), erreurs),
            "georisques": _safe_call(
                "georisques",
                georisques_connector.fetch_georisques(client, geocode.citycode, geocode.lat, geocode.lon),
                erreurs,
            ),
            "altitude": _safe_call(
                "ign_altitude",
                ign_altitude.fetch_altitude(client, geocode.lat, geocode.lon),
                erreurs,
            ),
            "climat": _safe_call(
                "open_meteo",
                open_meteo.fetch_climate_summary(client, geocode.lat, geocode.lon),
                erreurs,
            ),
        }

        # DVF (lookup local synchrone, CSV a telecharger a la main - cf.
        # settings.dvf_enabled/DVF_ENABLED) et Copernicus (CDS, potentiel
        # premier telechargement multi-gigaoctets) sont tous deux optionnels
        # et geres de la meme facon : desactives -> valeur None, sans
        # ajouter d'erreur (ce n'est pas un echec, juste une source coupee
        # volontairement sur ce poste).
        if enable_dvf:
            tasks["dvf"] = _safe_call(
                "dvf_local", asyncio.to_thread(dvf_lookup.lookup_dvf, geocode.citycode), erreurs
            )
        else:
            logger.info("  dvf desactive (flag=False) -> dvf_local = None")

        if enable_copernicus:
            tasks["copernicus"] = _safe_call(
                "copernicus",
                asyncio.to_thread(copernicus.read_indicators_at_point, geocode.lat, geocode.lon),
                erreurs,
            )
        else:
            logger.info("  copernicus desactive (flag=False) -> climat_copernicus = None")

        keys = list(tasks.keys())
        results = await asyncio.gather(*(tasks[k] for k in keys))
        resolved = dict(zip(keys, results))

        bdnb_data = resolved["bdnb"]
        georisques_data = resolved["georisques"]
        altitude_m = resolved["altitude"]
        climat = resolved["climat"]
        dvf_data = resolved.get("dvf")
        climat_copernicus = resolved.get("copernicus")

    # Etape 3 - fan-in : assemblage du building_data final
    logger.info("etape 3/3 -- assemblage building_data (%d erreur(s) de source)", len(erreurs))
    building_data = {
        "adresse": {
            "label": geocode.label,
            "citycode": geocode.citycode,
            "postcode": geocode.postcode,
            "city": geocode.city,
            "score_geocodage": geocode.score,
            "lat": geocode.lat,
            "lon": geocode.lon,
        },
        "departement": department_code,
        "departement_nom": department_name(department_code),
        "dans_perimetre_paca": is_in_paca(geocode.citycode),
        "altitude_m": altitude_m,
        "bdnb": bdnb_data,
        "georisques": georisques_data or {"erreurs": ["georisques totalement indisponible"]},
        "climat_open_meteo": _climate_to_dict(climat),
        "climat_copernicus": climat_copernicus,
        "dvf_local": dvf_data,
        "erreurs": erreurs,
        "genere_le": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("collector_agent -- termine en %.2fs (%d erreur(s))", time.perf_counter() - t0, len(erreurs))
    return building_data


def _climate_to_dict(climate_summary) -> dict | None:
    if climate_summary is None:
        return None
    return {
        "modeles_utilises": climate_summary.modeles_utilises,
        "reference_2015_2024": vars(climate_summary.reference_2015_2024),
        "projection_2041_2050": vars(climate_summary.projection_2041_2050),
    }
