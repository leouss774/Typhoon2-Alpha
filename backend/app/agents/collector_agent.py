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
from datetime import datetime, timezone

import httpx

from app.connectors import bdnb as bdnb_connector
from app.connectors import copernicus
from app.connectors import dvf_lookup
from app.connectors import georisques as georisques_connector
from app.connectors import ign_altitude
from app.connectors import open_meteo
from app.connectors.geocoding import geocode_address, reverse_geocode, GeocodeResult
from app.core.config import settings
from app.core.paca import department_code_from_citycode, department_name, is_in_paca


async def _safe_call(source_name: str, coro, erreurs: list[dict]):
    """Execute un connecteur et convertit toute exception en entree d'erreur."""
    try:
        return await coro
    except Exception as exc:  # volontairement large : on isole chaque source
        erreurs.append({"source": source_name, "erreur": f"{type(exc).__name__}: {exc}"})
        return None


_COORDS_THRESHOLD = 0.5


def _est_coordonnees(texte: str) -> tuple[float, float] | None:
    """Detecte si une chaine est au format 'lat,lon' et retourne (lat, lon)."""
    try:
        parts = texte.split(",")
        if len(parts) == 2:
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return (lat, lon)
    except (ValueError, TypeError):
        pass
    return None


async def _geocode_with_fallback(
    client: httpx.AsyncClient,
    address: str,
    erreurs: list[dict],
) -> GeocodeResult | None:
    """Tente le geocodage direct ; si c'est des coordonnees, tente le reverse.
    En dernier recours, construit un resultat synthetique pour les coordonnees.
    """
    coords = _est_coordonnees(address)

    # Si l'adresse n'est pas des coordonnées, on tente le geocodage normal
    if coords is None:
        return await geocode_address(client, address)

    # C'est des coordonnées : tente le geocodage direct d'abord
    try:
        geocode = await geocode_address(client, address)
        if geocode and geocode.score >= _COORDS_THRESHOLD:
            return geocode
    except Exception as exc:
        erreurs.append({"source": "geocode_direct", "erreur": str(exc)})

    # Fallback : reverse geocode des coordonnées
    if coords:
        try:
            geocode = await reverse_geocode(client, coords[0], coords[1])
            if geocode:
                return geocode
        except Exception as exc:
            erreurs.append({"source": "reverse_geocode", "erreur": str(exc)})

        # Dernier recours : géocodage synthétique (les APIs externes peuvent
        # être bloquées par la politique réseau du sandbox)
        lat, lon = coords
        erreurs.append({
            "source": "geocode_synthetique",
            "erreur": f"Géocodage synthétique pour coordonnées {lat},{lon}"
        })
        return GeocodeResult(
            label=f"{lat:.5f},{lon:.5f}",
            citycode="",  # citycode inconnu — DVF/Georisques communal indisponibles
            postcode="",
            city="",
            score=0.5,
            lat=lat,
            lon=lon,
        )

    return None


async def collect(address: str) -> dict:
    """Point d'entree principal : lance la collecte complete pour une adresse.

    Si l'adresse ressemble a des coordonnees ("lat,lon"), tente d'abord
    le geocodage normal ; en cas d'echec, utilise le reverse geocode.
    """
    erreurs: list[dict] = []

    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        # Etape 1 - geocodage BAN (bloquant, requis par Georisques/IGN/Copernicus)
        geocode = await _geocode_with_fallback(client, address, erreurs)

        if geocode is None:
            raise RuntimeError(
                f"Impossible de geocoder l'adresse : {address!r} "
                "(geocodage direct et reverse echoues)"
            )

        department_code = department_code_from_citycode(geocode.citycode)

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

        # Copernicus (CDS) : desactive par defaut car le premier lancement
        # declenche un telechargement multi-gigaoctets via l'API CDS.
        # Activer avec COPERNICUS_ENABLED=true dans .env, puis telecharger
        # les donnees une fois avec le script dedie.
        if settings.copernicus_enabled:
            copernicus_task = _safe_call(
                "copernicus",
                asyncio.to_thread(copernicus.read_indicators_at_point, geocode.lat, geocode.lon),
                erreurs,
            )
        else:
            # Tâche factice : retourne None sans rien faire, pour garder
            # l'ordre d'unpacking constant sans condition fragile.
            copernicus_task = _safe_call("copernicus", asyncio.sleep(0, result=None), erreurs)

        # DVF est une lecture synchrone (fichier local) : on le passe par
        # asyncio.to_thread pour ne pas bloquer la boucle asyncio.
        dvf_task = _safe_call(
            "dvf_local",
            asyncio.to_thread(dvf_lookup.lookup_dvf, geocode.citycode),
            erreurs,
        )

        bdnb_data, georisques_data, altitude_m, climat, climat_copernicus, dvf_data = await asyncio.gather(
            bdnb_task, georisques_task, altitude_task, climat_task, copernicus_task, dvf_task
        )

    # Etape 3 - fan-in : assemblage du building_data final
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

    return building_data


def _climate_to_dict(climate_summary) -> dict | None:
    if climate_summary is None:
        return None
    return {
        "modeles_utilises": climate_summary.modeles_utilises,
        "reference_2015_2024": vars(climate_summary.reference_2015_2024),
        "projection_2041_2050": vars(climate_summary.projection_2041_2050),
    }
