from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.connectors import bdnb, geocoding, georisques, georisques_v2, wfs
from app.core.config import settings
from app.core.logging import get_logger
from app.scoring.zone_hazard_scores import apply_hazard_scores
from app.services.catnat_parse import merge_catnat, parse_catnat_from_georisques

logger = get_logger(__name__)

_ARROND_MAP: dict[str, str] = {
    "75101": "75056", "75102": "75056", "75103": "75056", "75104": "75056",
    "75105": "75056", "75106": "75056", "75107": "75056", "75108": "75056",
    "75109": "75056", "75110": "75056", "75111": "75056", "75112": "75056",
    "75113": "75056", "75114": "75056", "75115": "75056", "75116": "75056",
    "75117": "75056", "75118": "75056", "75119": "75056", "75120": "75056",
    "69381": "69123", "69382": "69123", "69383": "69123", "69384": "69123",
    "69385": "69123", "69386": "69123", "69387": "69123", "69388": "69123",
    "69389": "69123",
    "13201": "13055", "13202": "13055", "13203": "13055", "13204": "13055",
    "13205": "13055", "13206": "13055", "13207": "13055", "13208": "13055",
    "13209": "13055", "13210": "13055", "13211": "13055", "13212": "13055",
    "13213": "13055", "13214": "13055", "13215": "13055", "13216": "13055",
}

_NUM_RISQUE_MAP = {
    "11": "inondation",
    "113": "inondation",
    "114": "inondation",
    "12": "mouvement_terrain",
    "121": "mouvement_terrain",
    "122": "mouvement_terrain",
    "123": "mouvement_terrain",
    "124": "mouvement_terrain",
    "125": "mouvement_terrain",
    "126": "mouvement_terrain",
    "127": "mouvement_terrain",
    "13": "sismique",
    "16": "feu_foret",
    "18": "radon",
}

_RISQUE_LABEL_MAP = {
    "11": "Inondation",
    "113": "Crue torrentielle",
    "114": "Ruissellement",
    "12": "Mouvement de terrain",
    "121": "Affaissement/effondrement",
    "122": "Mouvement de terrain (122)",
    "123": "Eboullement",
    "124": "Glissement de terrain",
    "125": "Mouvement de terrain (125)",
    "126": "Mouvement de terrain (126)",
    "127": "Tassements differentiels",
    "13": "Seisme",
    "16": "Feu de foret",
    "18": "Radon",
}


async def _safe_call(name: str, coro, errors: list[dict]):
    try:
        result = await coro
        errors.append({"source": name, "ok": True})
        return result
    except Exception as exc:
        logger.warning("  [%s] ECHEC -> %s: %s", name, type(exc).__name__, exc)
        errors.append({"source": name, "ok": False, "error": str(exc)})
        return None


def _find_risques_detail(geo_data: dict) -> list[dict]:
    data_list = geo_data.get("risques_commune") or {}
    if isinstance(data_list, dict):
        data_arr = data_list.get("data") or []
        if data_arr and isinstance(data_arr[0], dict):
            return data_arr[0].get("risques_detail") or []
    return []


def _parse_risques_hazards(risques_detail: list[dict]) -> list[dict]:
    found: set[str] = set()
    hazards: list[dict] = []
    for item in risques_detail:
        num = item.get("num_risque")
        hazard_id = _NUM_RISQUE_MAP.get(num)
        if hazard_id and hazard_id not in found:
            found.add(hazard_id)
            label = _RISQUE_LABEL_MAP.get(num, item.get("libelle_risque_long", hazard_id))
            hazards.append({"hazard": hazard_id, "label": label, "level": "Present"})
    return hazards


def _level_from_class(raw: str | None) -> str | None:
    if raw is None:
        return None
    m = {"1": "Faible", "2": "Moyen", "3": "Eleve"}
    return m.get(raw.strip(), raw)


async def collect_point(lat: float, lon: float, address_label: str | None = None) -> dict[str, Any]:
    errors: list[dict] = []
    async with httpx.AsyncClient(timeout=settings.http_timeout_seconds) as client:
        try:
            geocode_input = address_label if (address_label and "," not in address_label) else f"{lat},{lon}"
            geo = await geocoding.geocode_address(client, geocode_input)
            citycode = geo.citycode
            resolved_label = geo.label
        except Exception as exc:
            logger.warning("geocoding ECHEC for %f,%f: %s", lat, lon, exc)
            citycode = None
            resolved_label = address_label or f"{lat:.5f},{lon:.5f}"

        parent_citycode = _ARROND_MAP.get(citycode) if citycode else None

        # Plan all concurrent calls
        tasks_def: list[tuple[str, Any]] = []
        code = citycode or "00000"
        tasks_def.append(("georisques", _safe_call("georisques", georisques.fetch_georisques(client, code, lat, lon), errors)))
        if parent_citycode:
            tasks_def.append(("georisques_parent", _safe_call("georisques_parent", georisques.fetch_georisques(client, parent_citycode, lat, lon), errors)))
        tasks_def.append(("georisques_v2", _safe_call("georisques_v2", georisques_v2.fetch_rga_v2(client, lat, lon), errors)))
        tasks_def.append(("wfs", _safe_call("wfs", wfs.fetch_distances(client, lat, lon), errors)))

        bdnb_enabled = bool(resolved_label and "," not in resolved_label)
        if bdnb_enabled:
            tasks_def.append(("bdnb", _safe_call("bdnb", bdnb.fetch_bdnb(client, resolved_label), errors)))
        else:
            errors.append({"source": "bdnb", "ok": False, "error": "skipped"})

        keys = [t[0] for t in tasks_def]
        coros = [t[1] for t in tasks_def]
        vals = await asyncio.gather(*coros)
        resolved = dict(zip(keys, vals))

    geo_data = resolved.get("georisques") or {}
    geo_parent = resolved.get("georisques_parent")
    wfs_data = resolved.get("wfs") or {}
    v2_data = resolved.get("georisques_v2")
    bdnb_data = resolved.get("bdnb")

    hazards: list[dict] = []

    # 1. Parse risques_detail from Georisques v1 (fallback to parent citycode if empty)
    risques_detail = _find_risques_detail(geo_data)
    if not risques_detail and geo_parent:
        risques_detail = _find_risques_detail(geo_parent)
    v1_hazards = _parse_risques_hazards(risques_detail)
    hazards.extend(v1_hazards)

    # 2. RGA v2 override
    rga_level = None
    if v2_data:
        content = v2_data.get("content") or []
        if content:
            rga_level = content[0].get("alea", "Present")
    if rga_level:
        hazards = [h for h in hazards if h["hazard"] != "rga_argile"]
        hazards.append({"hazard": "rga_argile", "label": "Retrait-gonflement argiles", "level": rga_level})

    # 3. Sismique depuis l'endpoint dedie
    sismique_data = geo_data.get("zonage_sismique") or {}
    sismique_raw = None
    if isinstance(sismique_data, dict):
        sismique_list = sismique_data.get("data") or []
        if sismique_list:
            sismique_raw = sismique_list[0].get("zone_sismicite") or sismique_list[0].get("libelle")
    if sismique_raw:
        hazards = [h for h in hazards if h["hazard"] != "sismique"]
        hazards.append({"hazard": "sismique", "label": "Seisme", "level": sismique_raw})

    # 4. Radon depuis l'endpoint dedie
    radon_data = geo_data.get("radon") or {}
    radon_raw = None
    if isinstance(radon_data, dict):
        radon_list = radon_data.get("data") or []
        if radon_list:
            radon_cls = radon_list[0].get("classe_potentiel") or radon_list[0].get("libelle")
            radon_raw = _level_from_class(radon_cls)
    if radon_raw:
        hazards = [h for h in hazards if h["hazard"] != "radon"]
        hazards.append({"hazard": "radon", "label": "Radon", "level": radon_raw})

    # 5. CATNAT by type (commune + parent arrondissement if used for risques)
    catnat_by_type = parse_catnat_from_georisques(geo_data)
    if geo_parent:
        catnat_by_type = merge_catnat(catnat_by_type, parse_catnat_from_georisques(geo_parent))
    catnat_total = catnat_by_type.get("total", 0)

    # 6. BDNB geometry
    bdnb_batiment = None
    bdnb_geom = None
    bdnb_cle = None
    if bdnb_data and isinstance(bdnb_data, dict):
        bdnb_batiment = bdnb_data.get("batiment")
        bdnb_cle = bdnb_data.get("cle_interop_adr")
        if bdnb_batiment and isinstance(bdnb_batiment, dict):
            bdnb_geom = (bdnb_batiment.get("geom") or bdnb_batiment.get("geometry")
                         or bdnb_batiment.get("geojson") or bdnb_batiment.get("geometrie"))

    point = {
        "address_label": resolved_label,
        "lat": lat,
        "lon": lon,
        "hazards": hazards,
        "catnat_total": catnat_total,
        "catnat_by_type": catnat_by_type,
        "distance_cours_eau_m": wfs_data.get("distance_cours_eau_m"),
        "distance_foret_m": wfs_data.get("distance_foret_m"),
        "bdnb_cle_interop_adr": bdnb_cle,
        "bdnb_geom": bdnb_geom,
        "source": "live",
        "errors": errors,
    }
    apply_hazard_scores(point)
    return point
