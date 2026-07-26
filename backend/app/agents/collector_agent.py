"""
collector_agent : orchestrateur de collecte de donnees.

C'est le premier noeud du graphe LangGraph decrit dans le README
(voir "Architecture multi-agents"). Cette version est un agent "test" :
il ne depend pas encore de LangGraph, pour permettre de valider rapidement
la connectivite reelle aux sources avant de le brancher dans le
StateGraph complet (scoring_agent, rag_agent, digital_twin_agent).

Sequence :
    1. Geocodage BAN de l'adresse -> lat/lon/citycode (bloquant, requis par
       Georisques, IGN Altitude et Copernicus).
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
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone

import httpx

from app.connectors import bdnb as bdnb_connector
from app.connectors import copernicus
from app.connectors import dvf_lookup
from app.connectors import georisques as georisques_connector
from app.connectors import ign_altitude
from app.connectors import open_meteo
from app.connectors.geocoding import geocode_address
from app.core.config import settings
from app.core.logging import get_logger
from app.core.paca import department_code_from_citycode, department_name, is_in_paca

logger = get_logger(__name__)


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


async def collect(address: str) -> dict:
    """Point d'entree principal : lance la collecte complete pour une adresse."""
    logger.info("collector_agent -- debut collecte pour %r", address)
    t0 = time.perf_counter()
    erreurs: list[dict] = []

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        # Etape 1 - geocodage BAN (bloquant, requis par Georisques/IGN/Copernicus)
        logger.info("etape 1/3 -- geocodage BAN")
        geocode = await geocode_address(client, address)
        logger.info(
            "  -> %s (citycode=%s, lat=%.5f, lon=%.5f, score=%.2f)",
            geocode.label, geocode.citycode, geocode.lat, geocode.lon, geocode.score,
        )

        department_code = department_code_from_citycode(geocode.citycode)

        logger.info("etape 2/3 -- collecte parallele (bdnb, georisques, ign_altitude, open_meteo, copernicus, dvf_local)")
        # Etape 2 - fan-out : toutes les sources live + lookups en parallele.
        # BDNB utilise son propre geocodeur interne (voir bdnb.py) : on lui
        # passe l'adresse brute, pas les coordonnees BAN.
        bdnb_task = _safe_call("bdnb", bdnb_connector.fetch_bdnb(client, address), erreurs)
        georisques_task = _safe_call(
            "georisques",
            georisques_connector.fetch_georisques(client, geocode.citycode, geocode.lat, geocode.lon),
            erreurs,
        )
        altitude_task = _safe_call(
            "ign_altitude",
            ign_altitude.fetch_altitude(client, geocode.lat, geocode.lon),
            erreurs,
        )
        climat_task = _safe_call(
            "open_meteo",
            open_meteo.fetch_climate_summary(client, geocode.lat, geocode.lon),
            erreurs,
        )

        # Copernicus (CDS) et DVF sont des lectures potentiellement longues
        # (premier telechargement CDS) ou synchrones (fichier local) : on
        # les passe par asyncio.to_thread pour ne pas bloquer la boucle
        # asyncio tout en restant dans le meme fan-out.
        copernicus_task = _safe_call(
            "copernicus",
            asyncio.to_thread(copernicus.read_indicators_at_point, geocode.lat, geocode.lon),
            erreurs,
        )
        dvf_task = _safe_call(
            "dvf_local",
            asyncio.to_thread(dvf_lookup.lookup_dvf, geocode.citycode),
            erreurs,
        )

        bdnb_data, georisques_data, altitude_m, climat, climat_copernicus, dvf_data = await asyncio.gather(
            bdnb_task, georisques_task, altitude_task, climat_task, copernicus_task, dvf_task
        )

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
