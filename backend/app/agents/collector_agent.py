"""collector_agent : orchestrateur de collecte de données.

Séquence : géocodage → fan-out BDNB/Georisques/IGN/Open-Meteo → fan-in.
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
from app.connectors import georisques as georisques_connector
from app.connectors import ign_altitude
from app.connectors import open_meteo
from app.connectors.geocoding import GeoResult, geocode_address, reverse_geocode
from app.core.config import settings
from app.core.logging import get_logger
from app.core.paca import department_code_from_citycode, department_name, is_in_paca

logger = get_logger(__name__)

_LATLON_RE = re.compile(r"^\s*(-?\d{1,2}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\s*$")


async def _safe_call(source_name: str, coro, erreurs: list[dict]):
    started = time.perf_counter()
    try:
        result = await coro
        logger.info("  [%s] OK (%.2fs)", source_name, time.perf_counter() - started)
        return result
    except Exception as exc:
        logger.warning("  [%s] ECHEC (%.2fs) -> %s: %s", source_name, time.perf_counter() - started, type(exc).__name__, exc)
        erreurs.append({"source": source_name, "erreur": f"{type(exc).__name__}: {exc}"})
        return None


async def _fetch_bdnb_avec_repli(client: httpx.AsyncClient, address: str, label_ban: str) -> dict | None:
    try:
        return await bdnb_connector.fetch_bdnb(client, label_ban)
    except BdnbAdresseIntrouvable:
        if label_ban == address:
            raise
        logger.info("  [bdnb] libellé BAN non trouvé, nouvel essai avec adresse brute")
        return await bdnb_connector.fetch_bdnb(client, address)


async def collect(address: str) -> dict:
    """Point d'entrée principal : lance la collecte complète pour une adresse."""
    logger.info("collector_agent -- début collecte pour %r", address)
    t0 = time.perf_counter()
    erreurs: list[dict] = []

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        # Étape 1 - géocodage
        logger.info("étape 1/3 -- géocodage")
        latlon_match = _LATLON_RE.match(address)
        try:
            if latlon_match:
                lat_in, lon_in = float(latlon_match.group(1)), float(latlon_match.group(2))
                geocode = await reverse_geocode(client, lat_in, lon_in)
                logger.info("  -> reverse geocode %s", geocode.label)
            else:
                geocode = await geocode_address(client, address)
                logger.info("  -> %s (score=%.2f)", geocode.label, geocode.score)
        except Exception as exc:
            logger.error("géocodage -- échec pour %r: %s", address, exc)
            erreurs.append({"source": "geocoding", "erreur": f"{type(exc).__name__}: {exc}"})
            # GeoResult vide pour permettre à la collecte de continuer
            geocode = GeoResult(
                label=address,
                citycode="",
                postcode="",
                city="",
                lat=0.0,
                lon=0.0,
                score=0.0,
            )

        department_code = department_code_from_citycode(geocode.citycode)

        # Étape 2 - fan-out
        logger.info("étape 2/3 -- collecte parallèle")
        tasks: dict[str, Awaitable] = {
            "bdnb": _safe_call("bdnb", _fetch_bdnb_avec_repli(client, address, geocode.label), erreurs),
            "georisques": _safe_call(
                "georisques",
                georisques_connector.fetch_georisques(client, geocode.citycode, geocode.lat, geocode.lon),
                erreurs,
            ),
            "altitude": _safe_call("ign_altitude", ign_altitude.fetch_altitude(client, geocode.lat, geocode.lon), erreurs),
            "climat": _safe_call("open_meteo", open_meteo.fetch_climate_summary(client, geocode.lat, geocode.lon), erreurs),
        }

        keys = list(tasks.keys())
        results = await asyncio.gather(*(tasks[k] for k in keys))
        resolved = dict(zip(keys, results))

        bdnb_data = resolved["bdnb"]
        georisques_data = resolved["georisques"]
        altitude_m = resolved["altitude"]
        climat = resolved["climat"]

    # Étape 3 - assemblage
    logger.info("étape 3/3 -- assemblage (%d erreur(s))", len(erreurs))
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
        "georisques": georisques_data or {"erreurs": ["georisques indisponible"]},
        "climat_open_meteo": _climate_to_dict(climat),
        "climat_copernicus": None,
        "dvf_local": None,
        "erreurs": erreurs,
        "genere_le": datetime.now(timezone.utc).isoformat(),
    }

    logger.info("collector_agent -- terminé en %.2fs (%d erreur(s))", time.perf_counter() - t0, len(erreurs))
    return building_data


def _climate_to_dict(climate_summary) -> dict | None:
    if climate_summary is None:
        return None
    return {
        "modeles_utilises": climate_summary.modeles_utilises,
        "reference_2015_2024": vars(climate_summary.reference_2015_2024),
        "projection_2041_2050": vars(climate_summary.projection_2041_2050),
    }
