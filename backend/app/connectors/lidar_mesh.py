"""
Phase 3b du plan jumeau 3D : maillage reel du batiment.

Au lieu de la boite procedurale (footprint + hauteur assumee), on construit
un maillage qui suit la surface reellement mesuree par le LiDAR HD :

  - Toit : triangulation de Delaunay des points LiDAR classe `batiment` (6),
    filtree par pente (seuls les triangles quasi-horizontaux sont gardes, ce
    qui rejette les facettes de facade) et par longueur d'arete (les
    triangles "ponts" sur les concavites sont coupes).
  - Murs : extrusion du footprint BDNB (`geom_groupe`, deja en Lambert-93),
    depuis le sol jusqu'a la hauteur du toit AU BORD de l'empreinte (hauteur
    de l'avant-toit, par sommet — on suit la pente reelle). Sans footprint,
    un alpha-shape du nuage (bati en L/U inclus).
  - Texture du toit : BD ORTHO IGN (WMTS `ORTHOIMAGERY.ORTHOPHOTOS`,
    TILEMATRIXSET `PM_0_19`, ~20 cm) — projection orthogonale des sommets du
    toit sur les tuiles telechargees.
  - Export GLB (scene trimesh : noeud `toit` texture + noeud `murs` colore),
    cache sur disque par batiment (`backend/cache/lidar_mesh/{id}.glb`).

Non bloquant : toute erreur leve `MeshIndisponible`, l'appelant retombe sur
le nuage de points (Track A) puis sur la geometrie procedurale.

Dependances : numpy, scipy (Delaunay), pillow (BD ORTHO), trimesh (GLB) —
importees paresseusement pour ne pas alourdir l'import de l'API.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import math
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# BD ORTHO WMTS — TILEMATRIXSET PM_0_19 (zoom max 19, ~20 cm au sol).
_WMTS_URL = "https://data.geopf.fr/wmts"
_ORTHO_LAYER = "ORTHOIMAGERY.ORTHOPHOTOS"
_ORTHO_Z = 19
_ORTHO_SCALE = 1066.364791924893
_ORTHO_RES = 0.00028 * _ORTHO_SCALE  # metres / pixel (Web Mercator)
_ORTHO_TILE = 256 * _ORTHO_RES  # taille d'une tuile en metres
_ORTHO_HALF_WORLD = 20037508.342789  # demi-monde Web Mercator (metres)
_R_EARTH = 6378137.0

_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"

# Seuils de reconstruction.
_PENTE_MAX = 0.45  # |normale.y| / |normale| : toit accepte jusqu'a ~63° de pente
_ARETE_MAX_M = 5.0  # aretes plus longues = triangles "ponts" coupes
_ALPHA_CIRCONRADIUS_M = 3.5  # alpha-shape : rayon max du cercle circonscrit
_SOL_M = -0.25  # socle legerement sous le niveau du sol (zero = mediane sol)
_MIN_POINTS = 80  # en dessous, pas de maillage fiable -> fallback
_RAYON_AVANT_TOIT_M = 2.5  # points bati cherches autour d'un sommet du footprint
_MUR_BANDE_M = 1.0  # demi-largeur (m) de la bande BD ORTHO chevauchant le contour, projetee sur chaque mur

_CACHE_DIR = Path(__file__).resolve().parent.parent / "cache" / "lidar_mesh"
_CACHE_VERSION = "v3-murs-ortho"  # invalide les GLB anciens (murs beige) lors d'un changement de format


class MeshIndisponible(Exception):
    """Pas assez de points, WFS/COPC/WMTS injoignable, ou reconstruction impossible."""


# ---------------------------------------------------------------------------
# Web Mercator (tuiles BD ORTHO)
# ---------------------------------------------------------------------------

def _mercator(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 -> Web Mercator (metres). y croit vers le nord."""
    lon_r = math.radians(lon)
    lat_r = math.radians(lat)
    mx = _R_EARTH * lon_r
    my = _R_EARTH * math.log(math.tan(math.pi / 4 + lat_r / 2))
    return mx, my


def _uv_from_l93(
    lx: float, ly: float, west_m: float, north_m: float, img_w: int, img_h: int
) -> tuple[float, float]:
    """UV (0..1) dans la texture BD ORTHO d'un point en Lambert-93.

    Meme projection que le toit : u = Est mercator, v = 1 - (Nord mercator)
    (v croit vers le sud).
    """
    mx, my = _mercator(*_l93_to_wgs84(lx, ly))
    return (
        (mx - west_m) / (_ORTHO_RES * img_w),
        1.0 - (north_m - my) / (_ORTHO_RES * img_h),
    )


def _tile_range(bbox_wgs84: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """(min_col, min_row, max_col, max_row) des tuiles couvrant la bbox.

    La ligne 0 est la tuile la plus au NORD (my le plus grand -> (HW - my)
    le plus petit). On prend soin de ne pas croiser les deux bords.
    """
    west, south, east, north = bbox_wgs84
    mx0, my0 = _mercator(west, north)
    mx1, my1 = _mercator(east, south)
    col0 = int(math.floor((mx0 + _ORTHO_HALF_WORLD) / _ORTHO_TILE))
    col1 = int(math.floor((mx1 + _ORTHO_HALF_WORLD) / _ORTHO_TILE))
    row_top = int(math.floor((_ORTHO_HALF_WORLD - my0) / _ORTHO_TILE))  # bord nord
    row_bottom = int(math.floor((_ORTHO_HALF_WORLD - my1) / _ORTHO_TILE))  # bord sud
    return col0, row_top, col1, row_bottom


def _fetch_ortho_texture(bbox_wgs84: tuple[float, float, float, float]) -> tuple[Any, float, float]:
    """Tuiles BD ORTHO assemblees -> (PIL.Image, west_m, north_m).

    `west_m`/`north_m` = origine mercator du coin haut-gauche de l'image
    assemblee, pour projeter les sommets en UV.
    """
    from PIL import Image

    import httpx

    col0, row0, col1, row1 = _tile_range(bbox_wgs84)
    w = (col1 - col0 + 1) * 256
    h = (row1 - row0 + 1) * 256
    canvas = Image.new("RGB", (w, h))
    url = (
        f"{_WMTS_URL}?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0"
        f"&LAYER={_ORTHO_LAYER}&STYLE=normal&TILEMATRIXSET=PM_0_19"
        f"&TILEMATRIX={_ORTHO_Z}&FORMAT=image/jpeg"
    )
    with httpx.Client(timeout=25, headers={"User-Agent": _USER_AGENT}) as client:
        for col in range(col0, col1 + 1):
            for row in range(row0, row1 + 1):
                r = client.get(f"{url}&TILEROW={row}&TILECOL={col}")
                if r.status_code == 200 and r.content:
                    tile = Image.open(io.BytesIO(r.content)).convert("RGB")
                    canvas.paste(tile, ((col - col0) * 256, (row - row0) * 256))
    west_m = col0 * _ORTHO_TILE - _ORTHO_HALF_WORLD
    north_m = _ORTHO_HALF_WORLD - row0 * _ORTHO_TILE
    return canvas, west_m, north_m


# ---------------------------------------------------------------------------
# Footprint (murs)
# ---------------------------------------------------------------------------

def _footprint_from_geom(geom_groupe: dict[str, Any], cx_l93: float, cy_l93: float) -> np.ndarray | None:
    """Polygone local (x, z) du footprint BDNB — anneau exterieur le plus grand.

    Convention scene : x = Est (metres depuis le centroide), z = Sud. Le
    footprint est en L93 absolu ; on le recentre sur le meme centroide que
    les points LiDAR (centre de la bbox de requete).
    """
    if not isinstance(geom_groupe, dict):
        return None
    coords = geom_groupe.get("coordinates")
    if not coords:
        return None

    best: list[list[float]] | None = None
    best_area = 0.0

    def area2(ring: list[list[float]]) -> float:
        s = 0.0
        n = len(ring)
        for i in range(n):
            x1, y1 = ring[i]
            x2, y2 = ring[(i + 1) % n]
            s += x1 * y2 - x2 * y1
        return abs(s) / 2.0

    def walk(node: Any) -> None:
        nonlocal best, best_area
        if (
            isinstance(node, list)
            and len(node) >= 3
            and all(
                isinstance(p, list) and len(p) >= 2
                and isinstance(p[0], (int, float)) and isinstance(p[1], (int, float))
                for p in node
            )
        ):
            a = area2(node)  # type: ignore[arg-type]
            if a > best_area:
                best_area = a
                best = node  # type: ignore[assignment]
            return
        if isinstance(node, list):
            for sub in node:
                walk(sub)

    walk(coords)
    if not best or best_area <= 0:
        return None
    return np.array([[p[0] - cx_l93, -(p[1] - cy_l93)] for p in best], dtype="float64")


def _alpha_polygon(x: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Polygone (x, z) autour du nuage par alpha-shape (bati L/U inclus)."""
    from collections import Counter

    from scipy.spatial import Delaunay

    if len(x) < 4:
        raise MeshIndisponible("trop peu de points pour un footprint")
    pts = np.column_stack([x, z])
    tri = Delaunay(pts)

    keep = []
    for s in tri.simplices:
        p = pts[s]
        a, b, c = p[0], p[1], p[2]
        la = np.hypot(*(b - a))
        lb = np.hypot(*(c - b))
        lc = np.hypot(*(a - c))
        if max(la, lb, lc) > _ARETE_MAX_M * 2:
            continue
        # Aire 2D (produit vectoriel en 2D — np.cross 2D retire en numpy 2.x).
        area = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) / 2.0
        if area < 1e-9:
            continue
        R = (la * lb * lc) / (4.0 * area)  # rayon du cercle circonscrit
        if R <= _ALPHA_CIRCONRADIUS_M:
            keep.append(s)
    if not keep:
        raise MeshIndisponible("alpha-shape vide")

    edge_count: Counter = Counter()
    for s in keep:
        for i in range(3):
            e = tuple(sorted((int(s[i]), int(s[(i + 1) % 3]))))
            edge_count[e] += 1
    boundary = [e for e, n in edge_count.items() if n == 1]
    if not boundary:
        raise MeshIndisponible("bord alpha-shape vide")

    adj: dict[int, list[int]] = {}
    for a, b in boundary:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)

    start = boundary[0][0]
    order = [start]
    prev = -1
    cur = start
    while True:
        nxts = [n for n in adj.get(cur, []) if n != prev]
        if not nxts:
            break
        nxt = nxts[0]
        if nxt == start and len(order) > 2:
            break
        order.append(nxt)
        prev, cur = cur, nxt
        if len(order) > 100000:
            break
    if len(order) < 3:
        raise MeshIndisponible("polygone alpha-shape degenere")
    return pts[np.array(order)]


# ---------------------------------------------------------------------------
# Construction du maillage
# ---------------------------------------------------------------------------

def _roof_surface(bx: np.ndarray, by: np.ndarray, bz: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Toit : Delaunay sur (x, z), filtre pente + longueur d'arete."""
    from scipy.spatial import Delaunay

    pts = np.column_stack([bx, bz])
    tri = Delaunay(pts)
    verts: list[np.ndarray] = []
    faces: list[list[int]] = []
    vmap: dict[int, int] = {}

    for s in tri.simplices:
        p0, p1, p2 = pts[s[0]], pts[s[1]], pts[s[2]]
        la = np.hypot(*(p1 - p0))
        lb = np.hypot(*(p2 - p1))
        lc = np.hypot(*(p0 - p2))
        if max(la, lb, lc) > _ARETE_MAX_M:
            continue
        v01 = np.array([p1[0] - p0[0], by[s[1]] - by[s[0]], p1[1] - p0[1]])
        v02 = np.array([p2[0] - p0[0], by[s[2]] - by[s[0]], p2[1] - p0[1]])
        normal = np.cross(v01, v02)
        norm = np.linalg.norm(normal)
        if norm < 1e-9:
            continue
        # |normale.y| / |normale| : garde les toits, rejette les facades.
        if abs(normal[1]) / norm < _PENTE_MAX:
            continue
        f = []
        for si in s:
            if si not in vmap:
                vmap[si] = len(verts)
                verts.append(np.array([pts[si][0], by[si], pts[si][1]]))
            f.append(vmap[si])
        faces.append(f)

    if len(faces) < 10:
        raise MeshIndisponible("surface de toit trop petite")
    return np.array(verts), np.array(faces, dtype="int64")


def _eave_heights(poly: np.ndarray, roof_xyz: np.ndarray) -> np.ndarray:
    """Hauteur de l'avant-toit par sommet du footprint (repli : mediane)."""
    n = len(poly)
    rx, ry, rz = roof_xyz[:, 0], roof_xyz[:, 1], roof_xyz[:, 2]
    fallback = float(np.median(ry))
    top = np.zeros(n)
    for i in range(n):
        d = np.hypot(rx - poly[i][0], rz - poly[i][1])
        near = ry[d <= _RAYON_AVANT_TOIT_M]
        top[i] = float(np.max(near)) if near.size else fallback
    return np.maximum(top, 1.0)


def _walls_surface(
    poly: np.ndarray,
    roof_xyz: np.ndarray,
    y_ground: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, list[tuple[float, float, float, float]]]:
    """Murs : extrusion du footprint jusqu'a l'avant-toit (hauteur par sommet).

    Retourne (verts, faces, top, edges) — `top` = hauteur de l'avant-toit par
    sommet du footprint ; `edges` = (ax, az, bx, bz) par quad, dans le meme
    ordre que les quads (pour mapper la texture BD ORTHO sur les murs).
    """
    n = len(poly)
    cx = float(np.mean(poly[:, 0]))
    cz = float(np.mean(poly[:, 1]))
    top = _eave_heights(poly, roof_xyz)

    verts: list[np.ndarray] = []
    faces: list[list[int]] = []
    edges: list[tuple[float, float, float, float]] = []

    def add_quad(a: np.ndarray, ha: float, b: np.ndarray, hb: float) -> None:
        base = len(verts)
        va = np.array([a[0], y_ground, a[1]])
        vb = np.array([b[0], y_ground, b[1]])
        vc = np.array([b[0], hb, b[1]])
        vd = np.array([a[0], ha, a[1]])
        verts.extend([va, vb, vc, vd])
        nrm = np.cross(vb - va, vc - va)
        mid = (va + vb + vc) / 3.0
        outward = np.array([mid[0] - cx, 0.0, mid[2] - cz])
        if np.dot(nrm, outward) < 0:
            faces.append([base, base + 2, base + 1])
            faces.append([base, base + 3, base + 2])
        else:
            faces.append([base, base + 1, base + 2])
            faces.append([base, base + 2, base + 3])

    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        add_quad(a, top[i], b, top[(i + 1) % n])
        edges.append((float(a[0]), float(a[1]), float(b[0]), float(b[1])))

    # Socle bas (fermeture du bas, normale vers le bas).
    base0 = len(verts)
    for p in poly:
        verts.append(np.array([p[0], y_ground, p[1]]))
    for i in range(n):
        a = base0 + i
        b = base0 + (i + 1) % n
        faces.append([a, b, base0])

    return np.array(verts), np.array(faces, dtype="int64"), top, edges


# ---------------------------------------------------------------------------
# Assemblage + export GLB
# ---------------------------------------------------------------------------

def _l93_to_wgs84(x: float, y: float) -> tuple[float, float]:
    from pyproj import CRS, Transformer

    t = Transformer.from_crs(CRS("EPSG:2154"), CRS("EPSG:4326"), always_xy=True)
    lon, lat = t.transform(x, y)
    return lon, lat


def _bbox_wgs84(lidar: dict[str, Any], cx_l93: float, cy_l93: float) -> tuple[float, float, float, float]:
    bbox = lidar.get("bbox_l93")
    if bbox:
        west, south, east, north = bbox
        lon0, lat0 = _l93_to_wgs84(west, south)
        lon1, lat1 = _l93_to_wgs84(east, north)
        return (lon0, lat0, lon1, lat1)
    lon, lat = _l93_to_wgs84(cx_l93, cy_l93)
    d = 0.001
    return (lon - d, lat - d, lon + d, lat + d)


def _points_xyz(lidar: dict[str, Any]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(x, y, z, cls) bruts depuis le dict LiDAR (repere local viewer)."""
    pts = np.array(lidar["points"], dtype="float64")
    if pts.shape[0] < _MIN_POINTS:
        raise MeshIndisponible("pas assez de points LiDAR")
    x, y, z, cls = pts[:, 0], pts[:, 1], pts[:, 2], pts[:, 3].astype("int32")
    bmask = cls == 6
    if bmask.sum() < _MIN_POINTS:
        raise MeshIndisponible("pas assez de points batiment")
    return x, y, z, bmask


def _centroid_l93(lidar: dict[str, Any]) -> tuple[float, float]:
    bbox = lidar.get("bbox_l93")
    if bbox:
        return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0
    return 0.0, 0.0


def _compute_meta(lidar: dict[str, Any], geom_groupe: dict[str, Any] | None) -> dict[str, Any]:
    """Meta seule (footprint local + hauteurs) — sans texture BD ORTHO."""
    x, y, z, bmask = _points_xyz(lidar)
    bx, by, bz = x[bmask], y[bmask], z[bmask]
    cx_l93, cy_l93 = _centroid_l93(lidar)
    poly = _footprint_from_geom(geom_groupe, cx_l93, cy_l93)
    if poly is None:
        poly = _alpha_polygon(bx, bz)
    roof_verts, _ = _roof_surface(bx, by, bz)
    eave_top = _eave_heights(poly, roof_verts)
    return {
        "footprint": [[round(float(v[0]), 2), round(float(v[1]), 2)] for v in poly],
        "hauteur_max_m": round(float(np.max(by)), 2),
        "hauteur_murs_m": round(float(np.max(eave_top)), 2),
    }


def _build_glb(lidar: dict[str, Any], geom_groupe: dict[str, Any] | None) -> tuple[bytes, dict[str, Any]]:
    """Reconstruction complete -> (octets GLB, meta) ou leve MeshIndisponible.

    `meta` = { footprint (polygone local x,z), hauteur_max_m, hauteur_murs_m }
    — sert au front pour decouper les zones de risque sur la geometrie reelle.
    """
    x, y, z, bmask = _points_xyz(lidar)
    bx, by, bz = x[bmask], y[bmask], z[bmask]

    # --- Toit (surface reelle mesuree) ---
    roof_verts, roof_faces = _roof_surface(bx, by, bz)

    # --- Murs ---
    # Les points sont deja centres sur le centroid des points (repere local).
    # Le footprint BDNB est en L93 absolu : on le recentre sur le centroid de
    # la bbox de requete (≈ centroid des points, a < 2 m pres).
    bbox = lidar.get("bbox_l93")
    cx_l93 = (bbox[0] + bbox[2]) / 2.0 if bbox else 0.0
    cy_l93 = (bbox[1] + bbox[3]) / 2.0 if bbox else 0.0

    poly = _footprint_from_geom(geom_groupe, cx_l93, cy_l93)
    if poly is None:
        poly = _alpha_polygon(bx, bz)

    walls_verts, walls_faces, eave_top, wall_edges = _walls_surface(poly, roof_verts, _SOL_M)

    # --- Texture BD ORTHO sur le toit ---
    try:
        import trimesh

        from trimesh.visual import TextureVisuals
        from trimesh.visual.material import PBRMaterial
    except ImportError as exc:  # pragma: no cover
        raise MeshIndisponible(f"trimesh non installe : {exc}") from exc

    img, west_m, north_m = _fetch_ortho_texture(_bbox_wgs84(lidar, cx_l93, cy_l93))
    img = img.convert("RGB")
    img_w, img_h = img.size

    # UV top-down : u = (mx - west_m) / (res * w) ; v = 1 - (north_m - my) / (res * h).
    uv = np.zeros((len(roof_verts), 2), dtype="float64")
    for i, v in enumerate(roof_verts):
        uv[i] = _uv_from_l93(cx_l93 + v[0], cy_l93 - v[2], west_m, north_m, img_w, img_h)
    np.clip(uv, 0.0, 1.0, out=uv)

    roof_mesh = trimesh.Trimesh(
        vertices=roof_verts,
        faces=roof_faces,
        process=False,
        visual=TextureVisuals(
            uv=uv,
            material=PBRMaterial(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.9),
        ),
    )

    # Murs : projection verticale de la bande BD ORTHO chevauchant le contour
    # de l'empreinte. u suit le cote (vraie couleur le long de la rue) ; v
    # parcourt la bande [bord de toit (interieur) -> rue (exterieur)], etiree
    # verticalement sur la hauteur du mur (pas de donnee verticale dans une
    # ortho nadirale — on "peint" le mur avec la bande au droit de sa base).
    wall_uv = np.zeros((len(walls_verts), 2), dtype="float64")
    cx0, cz0 = float(np.mean(poly[:, 0])), float(np.mean(poly[:, 1]))
    for k, (ax, az, bx, bz) in enumerate(wall_edges):
        ua, _ = _uv_from_l93(cx_l93 + ax, cy_l93 - az, west_m, north_m, img_w, img_h)
        ub, _ = _uv_from_l93(cx_l93 + bx, cy_l93 - bz, west_m, north_m, img_w, img_h)
        midx, midz = (ax + bx) / 2.0, (az + bz) / 2.0
        dx, dz = midx - cx0, midz - cz0
        d = math.hypot(dx, dz)
        if d < 1e-9:
            v_in = v_out = 0.5
        else:
            ux, uz = dx / d, dz / d
            _, v_in = _uv_from_l93(
                cx_l93 + midx + ux * _MUR_BANDE_M, cy_l93 - (midz + uz * _MUR_BANDE_M),
                west_m, north_m, img_w, img_h,
            )
            _, v_out = _uv_from_l93(
                cx_l93 + midx - ux * _MUR_BANDE_M, cy_l93 - (midz - uz * _MUR_BANDE_M),
                west_m, north_m, img_w, img_h,
            )
        i0 = k * 4  # ordre des sommets du quad : va (pied a), vb (pied b), vc (tete b), vd (tete a)
        wall_uv[i0 + 0] = (ua, v_out)
        wall_uv[i0 + 1] = (ub, v_out)
        wall_uv[i0 + 2] = (ub, v_in)
        wall_uv[i0 + 3] = (ua, v_in)
    np.clip(wall_uv, 0.0, 1.0, out=wall_uv)

    walls_mesh = trimesh.Trimesh(
        vertices=walls_verts,
        faces=walls_faces,
        process=False,
        visual=TextureVisuals(
            uv=wall_uv,
            material=PBRMaterial(baseColorTexture=img, metallicFactor=0.0, roughnessFactor=0.95),
        ),
    )

    scene = trimesh.Scene()
    scene.add_geometry(roof_mesh, node_name="toit", geom_name="toit")
    scene.add_geometry(walls_mesh, node_name="murs", geom_name="murs")
    glb = scene.export(file_type="glb")
    return glb, _compute_meta(lidar, geom_groupe)


# ---------------------------------------------------------------------------
# Point d'entree (cache + fetch + reconstruction)
# ---------------------------------------------------------------------------

def _cache_key(geom_groupe: dict[str, Any] | None, lon: float | None, lat: float | None, building_id: str | None) -> str:
    if building_id:
        return f"{building_id}__{_CACHE_VERSION}"
    payload = geom_groupe if geom_groupe else f"{lon},{lat}"
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20] + "__" + _CACHE_VERSION


async def build_building_mesh(
    geom_groupe: dict[str, Any] | None,
    lon: float | None = None,
    lat: float | None = None,
    building_id: str | None = None,
) -> bytes | None:
    """Maillage GLB du batiment (cache disque par batiment), ou None.

    Le fetch LiDAR est async ; la reconstruction (CPU + tuiles BD ORTHO)
    tourne dans un executor. Toute erreur -> None : le front retombe sur le
    nuage de points puis le bati procedural.
    """
    glb, _meta = await _build_cached(geom_groupe, lon, lat, building_id)
    return glb


async def _build_cached(
    geom_groupe: dict[str, Any] | None,
    lon: float | None,
    lat: float | None,
    building_id: str | None,
) -> tuple[bytes | None, dict[str, Any] | None]:
    """Construit (GLB, meta) avec cache disque par batiment. Non bloquant."""
    from app.connectors.lidar_hd import fetch_building_lidar

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(geom_groupe, lon, lat, building_id)
    glb_file = _CACHE_DIR / f"{key}.glb"
    meta_file = _CACHE_DIR / f"{key}.json"

    if glb_file.exists():
        try:
            glb = glb_file.read_bytes()
            if meta_file.exists():
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
                return glb, meta
            # GLB en cache mais meta absente (cache ancien) : on reconstruit
            # SEULEMENT la meta (sans texture — ~5 s, puis mise en cache).
            lidar = await fetch_building_lidar(geom_groupe, lon=lon, lat=lat)
            if lidar and lidar.get("count"):
                import asyncio

                try:
                    meta = await asyncio.get_running_loop().run_in_executor(
                        None, _compute_meta, lidar, geom_groupe
                    )
                    meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
                except MeshIndisponible:
                    meta = None
                except Exception as exc:
                    logger.warning("  [lidar_mesh] meta seule impossible -> %s", exc)
                    meta = None
            else:
                meta = None
            return glb, meta
        except OSError as exc:
            logger.warning("  [lidar_mesh] cache illisible %s -> %s", glb_file, exc)

    lidar = await fetch_building_lidar(geom_groupe, lon=lon, lat=lat)
    if not lidar or not lidar.get("count"):
        return None, None

    import asyncio

    try:
        glb, meta = await asyncio.get_running_loop().run_in_executor(None, _build_glb, lidar, geom_groupe)
    except MeshIndisponible as exc:
        logger.info("  [lidar_mesh] reconstruction impossible -> %s", exc)
        return None, None
    except Exception as exc:
        logger.warning("  [lidar_mesh] erreur reconstruction -> %s: %s", type(exc).__name__, exc)
        return None, None

    try:
        glb_file.write_bytes(glb)
        meta_file.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        logger.warning("  [lidar_mesh] ecriture cache impossible -> %s", exc)
    return glb, meta


async def build_building_meta(
    geom_groupe: dict[str, Any] | None,
    lon: float | None = None,
    lat: float | None = None,
    building_id: str | None = None,
) -> dict[str, Any] | None:
    """Meta du maillage (footprint local, hauteurs) — lit le cache, sinon
    reconstruit (le GLB lui-meme n'est pas renvoye, juste la meta)."""
    glb, meta = await _build_cached(geom_groupe, lon, lat, building_id)
    return meta
