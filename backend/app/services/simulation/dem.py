"""
MNT RGE ALTI (IGN Geoplateforme) pour la simulation d'inondation.

La « baignoire » procedurale du moteur est remplacee, quand le relief reel
est disponible, par une vraie contrainte topographique : on recupere le
MNT RGE ALTI sur l'emprise de la simulation, puis le moteur submerge les
cellules dont l'altitude passe sous le niveau d'eau — les vallees et zones
basses s'inondent en premier, les hauteurs restent seches.

Source : WMS-Raster Geoplateforme (data.geopf.fr/wms-r/wms), couche
`RGEALTI-MNT_PYR-ZIP_FXX_LAMB93_WMS` (MNT RGE ALTI, France metropolitaine,
publique, sans cle). UNE SEULE requete GetMap renvoie le raster
d'elevations en GeoTIFF (Float32 non compresse) pour le bbox demande — pas
de quota point-par-point, donc pas de risque de rate-limit (l'API
d'altimetrie ponctuelle IGN plafonne a ~5 req/s : inutilisable pour un
raster 20x20 en 400 requetes).

Le GeoTIFF est lu en Python pur (entetes TIFF : IFD, tags, bande unique
non compressee) — aucune dependance GDAL/rasterio.

Echec tolere (fail-soft) : toute anomalie (reponse non-TIFF, compression,
raster non numerique, couverture partielle) renvoie None et le moteur
retombe sur son modele procedural — jamais un job en erreur pour cette
raison. Resultats mis en cache par adresse (10 min) : rejouer une
simulation ne re-interroge pas l'API.
"""

from __future__ import annotations

import math
import struct
import time

import httpx

from app.core.logging import get_logger
from app.services.simulation.engine import (
    GRID_N,
    NO_DATA_THRESHOLD,
    SEA_SENTINEL,
    SPAN_DEG,
)

logger = get_logger(__name__)

_WMS_R_URL = "https://data.geopf.fr/wms-r/wms"
_DEM_LAYER = "RGEALTI-MNT_PYR-ZIP_FXX_LAMB93_WMS"
_DEM_TIMEOUT_S = 12.0
_DEM_CACHE_TTL_S = 10 * 60  # cache des DEM reussis (10 min par adresse)
_DEM_FAIL_TTL_S = 60        # cache negatif des echecs (1 min)

# Cle = (lat, lon) arrondis (le bbox de simulation ne depend que de l'adresse) ;
# valeur = (timestamp, dem | None).
_DEM_CACHE: dict[tuple[float, float], tuple[float, list[list[float]] | None]] = {}


def _cache_key(lat: float, lon: float) -> tuple[float, float]:
    return (round(lat, 4), round(lon, 4))


def _wgs84_to_web_mercator(lat: float, lon: float) -> tuple[float, float]:
    """Lat/lon → EPSG:3857 (x estest, y croissant vers le nord)."""
    x = lon * 20037508.34 / 180.0
    y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
    return x, y * 20037508.34 / 180.0


async def fetch_dem_for_bbox(lat: float, lon: float) -> list[list[float]] | None:
    """Retourne la grille d'altitudes RGE ALTI (m) alignee sur le raster du
    moteur (lignes[0] = sud, colonnes[0] = ouest), ou None si indisponible.

    Mise en cache : meme adresse → meme bbox → meme MNT. Les echecs sont
    aussi mis en cache (bref) pour ne pas marteler le service.
    """
    key = _cache_key(lat, lon)
    cached = _DEM_CACHE.get(key)
    if cached is not None:
        age = time.time() - cached[0]
        ttl = _DEM_CACHE_TTL_S if cached[1] is not None else _DEM_FAIL_TTL_S
        if age < ttl:
            return cached[1]

    dem = await _fetch_dem_uncached(lat, lon)
    _DEM_CACHE[key] = (time.time(), dem)
    return dem


async def _fetch_dem_uncached(lat: float, lon: float) -> list[list[float]] | None:
    """GetMap RGE ALTI MNT (GeoTIFF Float32) + lecture du raster."""
    half = SPAN_DEG / 2
    x_west, y_north = _wgs84_to_web_mercator(lat + half, lon - half)
    x_east, y_south = _wgs84_to_web_mercator(lat - half, lon + half)

    params = {
        "SERVICE": "WMS",
        "VERSION": "1.3.0",
        "REQUEST": "GetMap",
        "LAYERS": _DEM_LAYER,
        "STYLES": "",
        "CRS": "EPSG:3857",
        "BBOX": f"{x_west:.1f},{y_south:.1f},{x_east:.1f},{y_north:.1f}",
        "WIDTH": str(GRID_N),
        "HEIGHT": str(GRID_N),
        "FORMAT": "image/tiff",
    }

    try:
        async with httpx.AsyncClient(timeout=_DEM_TIMEOUT_S) as client:
            resp = await client.get(_WMS_R_URL, params=params)
        resp.raise_for_status()
        if not resp.content or resp.content[:2] not in (b"II", b"MM"):
            logger.warning(
                "MNT RGE ALTI : reponse non-TIFF pour (%.4f, %.4f) (HTTP %s) — repli procedural",
                lat, lon, resp.status_code,
            )
            return None
        dem = _parse_tiff(resp.content, GRID_N, GRID_N)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning(
            "MNT RGE ALTI indisponible pour (%.4f, %.4f) : %s — repli procedural",
            lat, lon, type(exc).__name__,
        )
        return None

    if dem is None:
        logger.warning(
            "MNT RGE ALTI illisible pour (%.4f, %.4f) — repli procedural", lat, lon
        )
        return None

    # Les pixels « no-data » (ex. mer en bord de cote, -99999 chez RGE ALTI)
    # sont remplaces par SEA_SENTINEL : le moteur les reconnait comme « mer »
    # — exclues de ses statistiques de relief, mais submergees en premier.
    # On ne retombe sur le modele procedural que si le MNT est quasi vide.
    flat = [v for row in dem for v in row]
    valid = [v for v in flat if v >= NO_DATA_THRESHOLD]
    if not valid or len(valid) < GRID_N * GRID_N * 0.25:
        logger.warning(
            "MNT RGE ALTI quasi vide pour (%.4f, %.4f) (%d/%d) — repli procedural",
            lat, lon, len(valid), GRID_N * GRID_N,
        )
        return None
    return [
        [SEA_SENTINEL if v < NO_DATA_THRESHOLD else v for v in row] for row in dem
    ]


def _parse_tiff(blob: bytes, want_w: int, want_h: int) -> list[list[float]] | None:
    """Lit un GeoTIFF simple bande (Float32 ou Int16/Int32, non compresse)
    et renvoie la grille avec lignes[0] = SUD (le TIFF est stocke du nord
    au sud). None si le format n'est pas exploitable."""
    try:
        if blob[:2] == b"II":
            endian, order = "<", "little"
        elif blob[:2] == b"MM":
            endian, order = ">", "big"
        else:
            return None

        ifd_off = struct.unpack_from(endian + "I", blob, 4)[0]
        n_entries = struct.unpack_from(endian + "H", blob, ifd_off)[0]

        tags: dict[int, tuple[int, int, bytes]] = {}
        for i in range(n_entries):
            off = ifd_off + 2 + 12 * i
            tag, typ, count = struct.unpack_from(endian + "HHI", blob, off)
            tags[tag] = (typ, count, blob[off + 8 : off + 12])

        def tag_int(tag: int) -> int | None:
            info = tags.get(tag)
            if not info:
                return None
            typ, count, val = info
            if typ == 3:  # SHORT
                return struct.unpack(endian + "H", val[:2])[0]
            if typ == 4:  # LONG
                return struct.unpack(endian + "I", val)[0]
            return None

        width = tag_int(256)
        height = tag_int(257)
        bits = tag_int(258)
        compression = tag_int(259)
        sample_format = tag_int(339) or 1
        if width is None or height is None or bits is None:
            return None
        if compression != 1 or width != want_w or height != want_h:
            return None

        # Strip offsets / byte counts (une ou plusieurs bandes).
        strip_offsets = _tag_int_array(blob, endian, tags, 273)
        strip_counts = _tag_int_array(blob, endian, tags, 279)
        if not strip_offsets or not strip_counts:
            return None

        raw = bytearray()
        for off, count in zip(strip_offsets, strip_counts):
            raw += blob[off : off + count]

        n_pixels = width * height
        sample_bytes = bits // 8

        # Format de lecture selon (bits, sample_format) — Float32 (le cas
        # RGE ALTI) comme Int16/Int32 signe/non signe.
        if sample_format == 3 and bits >= 32:
            pix_fmt = "f"
        elif sample_format == 2:
            pix_fmt = "h" if bits == 16 else "i"
        else:
            pix_fmt = "H" if bits == 16 else "I"

        def read_pixel(i: int) -> float:
            chunk = raw[i * sample_bytes : (i + 1) * sample_bytes]
            return float(struct.unpack(endian + pix_fmt, chunk)[0])

        # TIFF : ligne 0 = nord. Le moteur attend lignes[0] = sud → flip Y.
        return [
            [read_pixel((height - 1 - row) * width + col) for col in range(width)]
            for row in range(height)
        ]
    except (struct.error, IndexError, ValueError):
        return None


def _tag_int_array(
    blob: bytes, endian: str, tags: dict, tag: int
) -> list[int] | None:
    """Tag 273/279 : valeurs inline si count <= 2, sinon offset vers le tableau."""
    info = tags.get(tag)
    if not info:
        return None
    typ, count, val = info
    if typ != 3 and typ != 4:
        return None
    item_size = 2 if typ == 3 else 4
    fmt = "H" if typ == 3 else "I"
    n_inline = 4 // item_size
    if count <= n_inline:
        return [struct.unpack(endian + fmt, val[i * item_size : (i + 1) * item_size])[0]
                for i in range(count)]
    offset = struct.unpack(endian + "I", val)[0]
    return [
        struct.unpack(endian + fmt, blob[offset + i * item_size : offset + (i + 1) * item_size])[0]
        for i in range(count)
    ]
