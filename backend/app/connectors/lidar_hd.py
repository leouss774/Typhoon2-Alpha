"""
Nuage de points LiDAR HD IGN pour un batiment.

Phase 2 du plan `plan_jumeau_numerique_3d.md` : au lieu de telecharger la
dalle LAZ complete (1 km², ~128 Mo), on exploite le format COPC
(Cloud-Optimized Point Cloud) : la dalle est indexee en octree et peut etre
requetee par plages HTTP (HTTP range requests). On ne telecharge donc que
les noeuds de l'octree qui intersectent l'empreinte du batiment — quelques
centaines de Ko au lieu de 128 Mo.

Pipeline :
  1. WFS `IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle` -> dalle(s) couvrant la bbox
     du batiment (EPSG:2154). La reponse contient l'URL directe du .copc.laz.
  2. `laspy.copc.CopcReader` (lecture distante par range requests) ->
     `spatial_query(bounds)` -> tous les points dans la bbox.
  3. Filtre `classification == 6` (batiment), + garde la classe 2 (sol) pour
     ancrer le niveau zero.
  4. Conversion dans le repere local du viewer : x = Est (metres), z = Sud
     (metres), y = altitude au-dessus du sol du point (metres). Meme
     convention que `app.digital_twin.footprint` (x = Est, z = Sud).

Le tout est non bloquant : si la dalle n'existe pas, que le WFS ou le COPC
est indisponible, on leve une exception claire que l'appelant peut
intercepter (fallback sur la geometrie procedurale, cf. scene-engine.js).

Dependances ajoutees : `laspy` + `lazrs` (lecture LAZ/COPC), `numpy`.
"""

from __future__ import annotations

import logging
import math
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# URL WFS Geoplateforme — dalles du nuage de points LiDAR HD (nuages CLASSIFIES).
_WFS_DALLES_URL = "https://data.geopf.fr/wfs/ows"
_WFS_TYPENAMES = "IGNF_NUAGES-DE-POINTS-LIDAR-HD:dalle"

# Classification ASPRS : 2 = sol, 6 = batiment. On garde aussi 9 (eau) et
# 5 (vegetation haute) ? Non — pour le jumeau, seul le bati nous interesse,
# plus le sol comme reference de hauteur.
_CLASSE_BATIMENT = 6
_CLASSES_GARDEES = (2, 6)

# Marge autour de l'empreinte du batiment pour capter les decroches de
# facade et la corniche (metres).
_MARGE_M = 2.0

# Demi-taille (metres) de la bbox de recherche quand on n'a QUE le point
# lon/lat (pas de footprint) : assez large pour couvrir un batiment typique.
_FALLBACK_DEMI_M = 15.0

# User-Agent requis par l'API de telechargement (403 sinon).
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"


class LidarHdIndisponible(Exception):
    """Dalle absente, WFS/COPC injoignable, ou aucun point batiment."""


def _bbox_lambert93(
    geom_groupe: dict[str, Any] | None,
    lon: float | None = None,
    lat: float | None = None,
    code_insee: str | None = None,
) -> tuple[float, float, float, float] | None:
    """Bbox (minx, miny, maxx, maxy) en EPSG:2154 autour du batiment.

    Si `geom_groupe` (deja en Lambert-93 dans la reponse BDNB) est
    disponible, on l'utilise directement (polygone exact + marge). Sinon,
    repli : conversion lon/lat -> Lambert-93 autour du point (approx.
    equirectangulaire locale, suffisante pour une bbox de recherche).
    """
    if isinstance(geom_groupe, dict) and geom_groupe.get("coordinates"):
        coords = geom_groupe["coordinates"]
        xs: list[float] = []
        ys: list[float] = []
        _collect = lambda node: None  # noqa: E731

        def walk(node: Any) -> None:
            if (
                isinstance(node, list)
                and len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], (int, float))
            ):
                xs.append(float(node[0]))
                ys.append(float(node[1]))
                return
            if isinstance(node, list):
                for sub in node:
                    walk(sub)

        walk(coords)
        if xs and ys:
            return (min(xs) - _MARGE_M, min(ys) - _MARGE_M, max(xs) + _MARGE_M, max(ys) + _MARGE_M)

    if lon is None or lat is None:
        return None
    # lon/lat (WGS84) -> Lambert-93 (approx. locale autour du point).
    # Lambert-93 : x = 700000 + (lon - 3°) * k, y = 12655600 + ... — on
    # utilise pyproj (deja une dependance du backend) pour etre exact.
    try:
        from pyproj import CRS, Transformer

        transformer = Transformer.from_crs(CRS("EPSG:4326"), CRS("EPSG:2154"), always_xy=True)
        x, y = transformer.transform(lon, lat)
        d = _FALLBACK_DEMI_M
        return (x - d, y - d, x + d, y + d)
    except Exception as exc:  # pragma: no cover - repli rare
        logger.warning("  [lidar_hd] conversion lon/lat -> L93 impossible : %s", exc)
        return None


async def _find_dalle_url(
    client: httpx.AsyncClient, bbox: tuple[float, float, float, float]
) -> str | None:
    """Interroge le WFS Geoplateforme pour trouver la dalle .copc.laz couvrant la bbox."""
    params = {
        "SERVICE": "WFS",
        "REQUEST": "GetFeature",
        "VERSION": "2.0.0",
        "TYPENAMES": _WFS_TYPENAMES,
        "outputFormat": "application/json",
        "bbox": f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]},EPSG:2154",
    }
    try:
        resp = await client.get(_WFS_DALLES_URL, params=params, timeout=20.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("  [lidar_hd] WFS dalles indisponible -> %s: %s", type(exc).__name__, exc)
        return None
    features = data.get("features") or []
    if not features:
        logger.info("  [lidar_hd] aucune dalle LiDAR HD pour la bbox %s", bbox)
        return None
    url = (features[0].get("properties") or {}).get("url")
    if not url:
        logger.warning("  [lidar_hd] dalle sans url : %s", features[0].get("properties"))
        return None
    return url


def _read_copc(url: str, bbox: tuple[float, float, float, float]) -> dict[str, Any]:
    """Lecture distante du COPC : noeuds intersectant la bbox, filtre classe.

    Retourne un dict `{ "points": [...], "count": n, "bbox": [...], ... }`
    ou leve LidarHdIndisponible. Bloquant (CPU + IO) — a appeler dans un
    thread (run_in_executor) cote FastAPI.
    """
    try:
        import numpy as np
        from laspy.copc import Bounds, CopcReader
    except ImportError as exc:  # pragma: no cover
        raise LidarHdIndisponible(f"laspy/numpy non installes : {exc}") from exc

    try:
        # CopcReader.open accepte une URL ; on installe un opener avec UA.
        import urllib.request

        opener = urllib.request.build_opener()
        opener.addheaders = [("User-Agent", _USER_AGENT)]
        urllib.request.install_opener(opener)

        reader = CopcReader.open(url)
    except Exception as exc:
        raise LidarHdIndisponible(f"COPC injoignable : {exc}") from exc

    try:
        bounds = Bounds(
            mins=np.array([bbox[0], bbox[1], -1000.0]),
            maxs=np.array([bbox[2], bbox[3], 10000.0]),
        )
        data = reader.spatial_query(bounds)
    except Exception as exc:
        raise LidarHdIndisponible(f"requete COPC impossible : {exc}") from exc

    if len(data) == 0:
        raise LidarHdIndisponible("aucun point LiDAR dans la bbox")

    # ScaledArrayView n'expose pas astype : passage par np.asarray.
    x = np.asarray(data.x, dtype="float64")
    y = np.asarray(data.y, dtype="float64")
    z = np.asarray(data.z, dtype="float64")
    cls = np.asarray(data.classification, dtype="int32")

    # Niveau du sol : mediane des points classe 2 (sol) dans la bbox.
    sol_mask = cls == 2
    if sol_mask.any():
        z_sol = float(np.median(z[sol_mask]))
    else:
        z_sol = float(np.percentile(z, 2))

    # Points batiment + sol, convertis en repere local viewer.
    garde = np.isin(cls, _CLASSES_GARDEES)
    xi = x[garde]
    yi = y[garde]
    zi = z[garde]
    ci = cls[garde]

    cx = float(np.mean(xi))
    cy = float(np.mean(yi))

    # Convention scene (cf. footprint.py) : x = Est, z = Sud, y = hauteur.
    points = [
        [round(float(px - cx), 2), round(float(pz - z_sol), 2), round(float(-(py - cy)), 2), int(pc)]
        for px, py, pz, pc in zip(xi, yi, zi, ci)
    ]

    return {
        "count": len(points),
        "batiment": int((ci == _CLASSE_BATIMENT).sum()),
        "sol": int((ci == 2).sum()),
        "hauteur_max_m": round(float(np.percentile(zi[ci == _CLASSE_BATIMENT], 98) - z_sol), 2)
        if (ci == _CLASSE_BATIMENT).any()
        else None,
        "bbox_l93": [round(float(v), 1) for v in bbox],
        "dalle": url.rsplit("/", 1)[-1],
        "points": points,
    }


async def fetch_building_lidar(
    geom_groupe: dict[str, Any] | None,
    lon: float | None = None,
    lat: float | None = None,
    code_insee: str | None = None,
) -> dict[str, Any] | None:
    """Point d'entree : bbox du batiment -> nuage de points LiDAR (ou None).

    Non bloquant : toute erreur est loggee et renvoie None (le front fait
    alors un fallback sur la geometrie procedurale). Le COPC est lu dans un
    thread (CPU + IO), le WFS en async.
    """
    bbox = _bbox_lambert93(geom_groupe, lon, lat, code_insee)
    if bbox is None:
        return None

    try:
        async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}) as client:
            url = await _find_dalle_url(client, bbox)
            if not url:
                return None
    except Exception as exc:
        logger.warning("  [lidar_hd] WFS impossible -> %s: %s", type(exc).__name__, exc)
        return None

    import asyncio

    try:
        return await asyncio.get_running_loop().run_in_executor(None, _read_copc, url, bbox)
    except LidarHdIndisponible as exc:
        logger.warning("  [lidar_hd] %s", exc)
        return None
    except Exception as exc:  # pragma: no cover - filet de securite
        logger.warning("  [lidar_hd] erreur inattendue -> %s: %s", type(exc).__name__, exc)
        return None
