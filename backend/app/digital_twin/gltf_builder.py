"""
gltf_builder — Pure Python glTF 2.0 (.glb) builder for building footprints.

Two builders coexist here :

1. `build_glb(ring, height_m, ...)` — the original extruded prism (floor slab +
   walls + flat roof, one material). Kept as the generic fallback (box) when
   no BDNB geometry is available.

2. `build_glb_bim(polygones, ...)` — the BIM-grade builder used by the
   `/diagnostic/adresse/gltf` endpoint when BDNB geometry is available :
     - real footprint : EVERY polygon of the MultiPolygon is extruded
       (`exterieur` + `trous` — courtyards become interior walls, no more box),
     - per-level floor slabs (one per `nb_niveau`, visible in section view),
     - pitched roof (`deux_pans` default) with a slope derived from the roof
       material (`pente_toit_deg`), ridge aligned on the dominant facade axis,
     - multi-material glTF : walls / roof / slabs each get their own primitive
       and material, colored from the BDNB material labels (`mat_mur_txt`,
       `mat_toit_txt`) via a small palette,
     - windows on the DPE-glazed facades (`l_orientation_baie_vitree` +
       `pourcentage_surface_baie_vitree_exterieur`) with translucent glass
       (alphaMode BLEND) + frames, and the entrance door on the street-facing
       facade estimated from the geocoded address.

No external dependencies — stdlib only (struct, json, math), like the rest of
the digital_twin package. glTF 2.0 spec:
  https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html

Coordinate system: glTF is right-handed Y-up. The footprint rings produced by
`footprint.extract_footprint` are already expressed in metres in the scene
frame (x = Est, z = Sud, nord vers -z). We map: local_x -> glTF X, height -> Y,
local_z -> glTF Z, exactly like `build_glb`.
"""

from __future__ import annotations

import json
import math
import struct
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# 1. Polygon helpers
# ---------------------------------------------------------------------------

Point2D = tuple[float, float]
Point3D = tuple[float, float, float]


def _signed_area_2d(ring: list[Point2D]) -> float:
    n = len(ring)
    total = 0.0
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _ensure_ccw(ring: list[Point2D]) -> list[Point2D]:
    """Ensure the ring is counter-clockwise (positive area) for glTF winding."""
    if _signed_area_2d(ring) < 0:
        return list(reversed(ring))
    return ring


def _cross_2d(o: Point2D, a: Point2D, b: Point2D) -> float:
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segment_intersects(p: Point2D, q: Point2D, a: Point2D, b: Point2D) -> bool:
    """Intersection PROPRE (intérieur des deux segments, pas seulement les
    extrémités) — le pont peut toucher un sommet existant sans croiser."""
    def orient(u: Point2D, v: Point2D, w: Point2D) -> float:
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])

    d1 = orient(a, b, p)
    d2 = orient(a, b, q)
    d3 = orient(p, q, a)
    d4 = orient(p, q, b)
    if ((d1 > 0 and d2 < 0) or (d1 < 0 and d2 > 0)) and (
        (d3 > 0 and d4 < 0) or (d3 < 0 and d4 > 0)
    ):
        return True
    return False


def _best_bridge_target(
    hj: Point2D, ring: list[Point2D], hole: list[Point2D]
) -> int:
    """Meilleur sommet du contour pour ancrer le pont depuis hj : à droite du
    trou (x >= x_hj) de préférence, visible (aucune arête croisée), sinon le
    plus proche visible."""
    best: int | None = None
    best_d = float("inf")
    for k, v in enumerate(ring):
        if math.dist(v, hj) < 1e-9:
            continue
        # Visibilité : le segment ne croise aucune arête du contour ni du trou.
        visible = True
        for edges in (ring, hole):
            n = len(edges)
            for e in range(n):
                a, b = edges[e], edges[(e + 1) % n]
                if _segment_intersects(hj, v, a, b):
                    visible = False
                    break
            if not visible:
                break
        if not visible:
            continue
        d = (v[0] - hj[0]) ** 2 + (v[1] - hj[1]) ** 2
        if v[0] >= hj[0] - 1e-9 and d < best_d:
            best, best_d = k, d
    if best is not None:
        return best
    # Repli : plus proche visible, à gauche s'il le faut.
    best = None
    best_d = float("inf")
    for k, v in enumerate(ring):
        if math.dist(v, hj) < 1e-9:
            continue
        visible = True
        for edges in (ring, hole):
            n = len(edges)
            for e in range(n):
                a, b = edges[e], edges[(e + 1) % n]
                if _segment_intersects(hj, v, a, b):
                    visible = False
                    break
            if not visible:
                break
        if visible:
            d = (v[0] - hj[0]) ** 2 + (v[1] - hj[1]) ** 2
            if d < best_d:
                best, best_d = k, d
    return best if best is not None else 0


def _point_in_ring_2d(point: Point2D, ring: list[Point2D]) -> bool:
    """Ray-casting point-in-polygon test (ring can be CW or CCW)."""
    x, y = point
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) / (y2 - y1) * (x2 - x1)
            if x_cross > x:
                inside = not inside
    return inside


def _triangulate_polygon(ring: list[Point2D]) -> list[tuple[int, int, int]]:
    """
    Ear-clipping triangulation for a simple convex or mildly concave polygon.
    Returns list of (i, j, k) index triples into `ring`.
    This is a simple O(n²) ear-clipper sufficient for building footprints
    (typically 4–20 vertices).
    """
    indices = list(range(len(ring)))
    triangles: list[tuple[int, int, int]] = []

    def _is_ear(a: int, b: int, c: int) -> bool:
        ax, ay = ring[a]
        bx, by = ring[b]
        cx, cy = ring[c]
        # Cross product of (b-a) x (c-a) : must be positive (CCW)
        cross = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if cross <= 0:
            return False
        # Check no other point is inside triangle abc
        for i in indices:
            if i in (a, b, c):
                continue
            px, py = ring[i]
            d1 = (bx - ax) * (py - ay) - (by - ay) * (px - ax)
            d2 = (cx - bx) * (py - by) - (cy - by) * (px - bx)
            d3 = (ax - cx) * (py - cy) - (ay - cy) * (px - cx)
            if d1 >= 0 and d2 >= 0 and d3 >= 0:
                return False
        return True

    while len(indices) > 3:
        n = len(indices)
        ear_found = False
        for i in range(n):
            a = indices[(i - 1) % n]
            b = indices[i]
            c = indices[(i + 1) % n]
            if _is_ear(a, b, c):
                triangles.append((a, b, c))
                indices.pop(i)
                ear_found = True
                break
        if not ear_found:
            # Degenerate polygon — just fan-triangulate from first vertex
            for i in range(1, len(indices) - 1):
                triangles.append((indices[0], indices[i], indices[i + 1]))
            break

    if len(indices) == 3:
        triangles.append((indices[0], indices[1], indices[2]))

    return triangles


def _earclip_robust(ring: list[Point2D]) -> list[tuple[int, int, int]]:
    """Ear-clipping tolerant of the zero-width bridge slits produced when
    merging holes : collinear (degenerate) ears are dropped instead of
    blocking the loop, so the slit never deadlocks the clipper."""
    idx = list(range(len(ring)))
    tris: list[tuple[int, int, int]] = []
    guard = 0
    while len(idx) > 3:
        guard += 1
        if guard > max(len(ring) * 40, 200):
            break
        n = len(idx)
        clipped = False
        for i in range(n):
            a, b, c = idx[(i - 1) % n], idx[i], idx[(i + 1) % n]
            cross = _cross_2d(ring[a], ring[b], ring[c])
            if abs(cross) <= 1e-9:
                # Ear dégénéré (fente du pont, doublon) : on retire le sommet
                # sans émettre de triangle.
                idx.pop(i)
                clipped = True
                break
            if cross <= 0:
                continue  # reflex
            # Aucun autre point à l'intérieur du triangle ? (les sommets
            # dupliqués par la fente sont coïncidents avec a/b/c : on les
            # ignore, sinon aucun ear ne passerait autour du pont).
            inside = False
            for k in idx:
                if k in (a, b, c):
                    continue
                if any(
                    math.dist(ring[k], ring[v]) < 1e-9 for v in (a, b, c)
                ):
                    continue
                d1 = _cross_2d(ring[a], ring[b], ring[k])
                d2 = _cross_2d(ring[b], ring[c], ring[k])
                d3 = _cross_2d(ring[c], ring[a], ring[k])
                if d1 > -1e-9 and d2 > -1e-9 and d3 > -1e-9:
                    inside = True
                    break
            if not inside:
                tris.append((a, b, c))
                idx.pop(i)
                clipped = True
                break
        if not clipped:
            # Coin coincident dégénéré : fan triangulation de secours.
            for i in range(1, len(idx) - 1):
                tris.append((idx[0], idx[i], idx[i + 1]))
            break
    if len(idx) == 3:
        tris.append((idx[0], idx[1], idx[2]))
    return tris


def _triangulate_polygon_with_holes(
    exterior: list[Point2D], holes: list[list[Point2D]]
) -> tuple[list[Point2D], list[tuple[int, int, int]]]:
    """
    Ear-clipping triangulation of a polygon with holes (bridge-cut method).

    Each hole (cour intérieure) is bridged to the exterior ring by a pair of
    coincident edges (the bridge vertex is duplicated at both ends), then the
    resulting simple polygon is ear-clipped by `_earclip_robust` which drops
    the degenerate slit ears. Robust enough for the courtyard shapes seen in
    BDNB data.

    Returns (merged_ring, triangles) where `triangles` index into
    `merged_ring`. With no holes, `merged_ring` is the exterior itself.
    """
    if not holes:
        return list(exterior), _triangulate_polygon(exterior)

    ring = list(exterior)
    # Ensure exterior CCW, holes CW — bridge-cut expects this orientation.
    if _signed_area_2d(ring) < 0:
        ring = list(reversed(ring))
    holes_norm: list[list[Point2D]] = []
    for h in holes:
        if len(h) < 3:
            continue
        hh = list(h)
        if _signed_area_2d(hh) > 0:
            hh = list(reversed(hh))
        holes_norm.append(hh)

    for hole in holes_norm:
        # Sommet le plus à droite du trou (max x) — ancre standard du pont.
        j = max(range(len(hole)), key=lambda k: hole[k][0])
        hj = hole[j]
        # Le pont doit être VISIBLE : le segment hj→p_i ne doit traverser ni
        # le trou ni le contour courant (sinon la triangulation se chevauche).
        # On préfère un sommet du contour situé À DROITE du trou (x >= x_hj),
        # sinon le pont passerait au travers de la cour.
        i = _best_bridge_target(hj, ring, hole)
        # Trou parcouru dans SON sens (CW) à partir du pont : le polygone
        # fusionné garde l'intérieur de la couronne à gauche (extérieur CCW,
        # trou CW — convention footprint.py). Les deux arêtes du couloir
        # (p_i→h_j puis h_j→p_i) sont coïncidentes : largeur nulle.
        hole_seq = [hole[(j + k) % len(hole)] for k in range(len(hole) + 1)]
        ring = ring[: i + 1] + hole_seq + [ring[i]] + ring[i + 1 :]

    triangles = _earclip_robust(ring)
    # Drop degenerate (zero-area) triangles produced by the bridges.
    kept: list[tuple[int, int, int]] = []
    for a, b, c in triangles:
        area = _cross_2d(ring[a], ring[b], ring[c])
        if abs(area) > 1e-6:
            kept.append((a, b, c))
    return ring, kept


# ---------------------------------------------------------------------------
# 2. Mesh builders (shared winding conventions)
# ---------------------------------------------------------------------------

def _tri_normal(a: Point3D, b: Point3D, c: Point3D) -> Point3D:
    """Unnormalised face normal (cross product)."""
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    return (uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx)


def _push_tri(
    verts: list[Point3D],
    tris: list[tuple[int, int, int]],
    a: Point3D,
    b: Point3D,
    c: Point3D,
    want_normal: Point3D | None = None,
) -> None:
    """Append triangle (a,b,c). If want_normal given, wind it so the face
    normal points along want_normal (outward/up) — robust to CW/CCW rings."""
    i = len(verts)
    verts.extend([a, b, c])
    if want_normal is None:
        tris.append((i, i + 1, i + 2))
        return
    n = _tri_normal(a, b, c)
    if n[0] * want_normal[0] + n[1] * want_normal[1] + n[2] * want_normal[2] < 0:
        tris.append((i, i + 2, i + 1))
    else:
        tris.append((i, i + 1, i + 2))


def _push_quad(
    verts: list[Point3D],
    tris: list[tuple[int, int, int]],
    a: Point3D,
    b: Point3D,
    c: Point3D,
    d: Point3D,
    want_normal: Point3D | None = None,
) -> None:
    _push_tri(verts, tris, a, b, c, want_normal)
    _push_tri(verts, tris, a, c, d, want_normal)


def _add_ring_walls(
    verts: list[Point3D],
    tris: list[tuple[int, int, int]],
    ring: list[Point2D],
    height: float,
) -> None:
    """One wall quad per edge of the ring.

    Winding convention (footprint.py) : exterior rings are CCW, holes (cours
    intérieures) are CW. The horizontal normal (dz, -dx) of a CCW edge points
    OUTWARD, and of a CW edge points INTO the courtyard — so the same formula
    produces facade walls for the exterior and courtyard walls for holes.
    """
    _add_ring_walls_band(verts, tris, ring, 0.0, height)


def _add_ring_walls_band(
    verts: list[Point3D],
    tris: list[tuple[int, int, int]],
    ring: list[Point2D],
    y0: float,
    y1: float,
) -> None:
    """Wall quads per edge of the ring between heights `y0` and `y1`.

    Variante `_add_ring_walls` tronquee a une bande d'etage : les murs sont
    decoupes en tranches horizontales (une par niveau) — c'est ce decoupage
    qui permet, cote viewer, de deplacer/cisailer chaque etage independamment
    (simulation sismique, effondrement en corps rigides).
    """
    if y1 - y0 < 1e-9:
        return
    n = len(ring)
    for i in range(n):
        x0, z0 = ring[i]
        x1, z1 = ring[(i + 1) % n]
        dx, dz = x1 - x0, z1 - z0
        length = math.hypot(dx, dz)
        if length < 1e-9:
            continue
        nx, nz = dz / length, -dx / length
        a = (x0, y0, z0)
        b = (x1, y0, z1)
        c = (x1, y1, z1)
        d = (x0, y1, z0)
        _push_quad(verts, tris, a, b, c, d, (nx, 0.0, nz))


_ORIENTATIONS = {"nord", "sud", "est", "ouest"}


def _facade_orientation(nx: float, nz: float) -> str:
    """Classe une normale horizontale de facade (nx, nz) en orientation
    cardinale (nord/sud/est/ouest). Repere scene : x = Est, z = Sud, donc le
    cap compas (0° = nord, horaire) de la normale vaut atan2(nx, -nz)."""
    bearing = math.degrees(math.atan2(nx, -nz)) % 360.0
    if 45.0 <= bearing < 135.0:
        return "est"
    if 135.0 <= bearing < 225.0:
        return "sud"
    if 225.0 <= bearing < 315.0:
        return "ouest"
    return "nord"


def _iter_exterior_edges(
    polygones: list[dict[str, Any]],
) -> list[tuple[Point2D, Point2D, float, Point2D]]:
    """Toutes les aretes des anneaux exterieurs (convention footprint.py :
    exterieur CCW), avec longueur et normale horizontale SORTANTE (nx, nz).
    Seuls les exterieurs portent fenetres/porte : une cour interieure n'a pas
    de facade sur rue."""
    edges: list[tuple[Point2D, Point2D, float, Point2D]] = []
    for poly in polygones:
        ext = poly.get("exterieur") or []
        if len(ext) < 3:
            continue
        if _signed_area_2d(ext) < 0:
            ext = list(reversed(ext))
        n = len(ext)
        for i in range(n):
            x0, z0 = ext[i]
            x1, z1 = ext[(i + 1) % n]
            length = math.hypot(x1 - x0, z1 - z0)
            if length < 1e-9:
                continue
            nx, nz = (z1 - z0) / length, -(x1 - x0) / length
            edges.append(((x0, z0), (x1, z1), length, (nx, nz)))
    return edges


def _edge_point(
    edge: tuple[Point2D, Point2D],
    length: float,
    normal: Point2D,
    u: float,
    v: float,
    offset: float,
) -> Point3D:
    """Point 3D sur un mur : abscisse `u` le long de l'arete, hauteur `v`,
    decale de `offset` le long de la normale sortante (fenetres/porte sont
    legerement en relief de la facade)."""
    (x0, z0), (x1, z1) = edge
    if length > 1e-9:
        px = x0 + (x1 - x0) * (u / length)
        pz = z0 + (z1 - z0) * (u / length)
    else:
        px, pz = x0, z0
    return (px + normal[0] * offset, v, pz + normal[1] * offset)


def _quad_on_edge(
    out: list[Point3D],
    tris: list[tuple[int, int, int]],
    edge: tuple[Point2D, Point2D],
    length: float,
    normal: Point2D,
    u0: float,
    u1: float,
    v0: float,
    v1: float,
    offset: float,
) -> None:
    """Quad vertical (vitre, bande de cadre, panneau de porte) pose sur une
    arete de facade, oriente selon la normale sortante."""
    a = _edge_point(edge, length, normal, u0, v0, offset)
    b = _edge_point(edge, length, normal, u1, v0, offset)
    c = _edge_point(edge, length, normal, u1, v1, offset)
    d = _edge_point(edge, length, normal, u0, v1, offset)
    _push_quad(out, tris, a, b, c, d, (normal[0], 0.0, normal[1]))


def _add_windows(
    glass_out: tuple[list[Point3D], list[tuple[int, int, int]]],
    frame_out: tuple[list[Point3D], list[tuple[int, int, int]]],
    edge: tuple[Point2D, Point2D],
    length: float,
    normal: Point2D,
    wall_h: float,
    floors: int,
    level_h: float,
    ratio: float,
    door_zone: tuple[float, float] | None = None,
) -> None:
    """Pose des fenetres sur une arete de facade vitree (DPE).

    La surface vitree vise `ratio` × surface du mur ; les fenetres sont
    reparties sur tous les etages (bande de mur entre 0.15 m et l'avant-toit
    moins 0.15 m), avec un cadre de 9 cm autour de chaque vitre. Le cadre est
    legerement plus en relief (offset 0.08) que la vitre (0.04).

    `door_zone` : intervalle d'abscisse [u0, u1] de la porte sur CE mur — les
    fenetres du rez-de-chaussee evitent alors la porte.
    """
    glass_v, glass_t = glass_out
    frame_v, frame_t = frame_out
    glazing = min(max(float(ratio), 0.03), 0.6)
    wall_area = length * wall_h
    band = max((wall_h - 0.3) / max(floors, 1), 0.3)
    wh = min(1.4, max(0.6, band * 0.8))
    per_floor = max(1, min(8, round(length / 3.2)))
    total = max(floors, 1) * per_floor
    ww = min(2.4, max(0.6, glazing * wall_area / (total * wh)))
    fw = 0.09
    for k in range(floors):
        v_lo = k * band + 0.15
        v_hi = min(v_lo + wh, (k + 1) * band + 0.15)
        for i in range(per_floor):
            u0 = max(0.2, (i + 0.5) * length / per_floor - ww / 2)
            u1 = min(length - 0.2, u0 + ww)
            if u1 - u0 < 0.35:
                continue
            if door_zone is not None and k == 0 and u0 < door_zone[1] and u1 > door_zone[0]:
                continue  # la porte occupe cette abscisse au rez-de-chaussee
            _quad_on_edge(glass_v, glass_t, edge, length, normal, u0, u1, v_lo, v_hi, 0.04)
            _quad_on_edge(frame_v, frame_t, edge, length, normal, u0 - fw, u0, v_lo - fw, v_hi + fw, 0.08)
            _quad_on_edge(frame_v, frame_t, edge, length, normal, u1, u1 + fw, v_lo - fw, v_hi + fw, 0.08)
            _quad_on_edge(frame_v, frame_t, edge, length, normal, u0, u1, v_hi, v_hi + fw, 0.08)
            _quad_on_edge(frame_v, frame_t, edge, length, normal, u0, u1, v_lo - fw, v_lo, 0.08)


def _add_door(
    door_out: tuple[list[Point3D], list[tuple[int, int, int]]],
    frame_out: tuple[list[Point3D], list[tuple[int, int, int]]],
    edge: tuple[Point2D, Point2D],
    length: float,
    normal: Point2D,
) -> tuple[float, float] | None:
    """Pose la porte d'entree (1.1 × 2.3 m, centree sur la facade rue) et son
    cadre. Retourne l'intervalle d'abscisse occupe (pour ecarter les fenetres
    du rez-de-chaussee) ou None si l'arete est trop courte."""
    door_v, door_t = door_out
    frame_v, frame_t = frame_out
    dw, dh = 1.1, 2.3
    u_lo = max(0.2, length / 2 - dw / 2)
    u_hi = min(length - 0.2, u_lo + dw)
    if u_hi - u_lo < 0.4:
        return None
    fw = 0.10
    _quad_on_edge(door_v, door_t, edge, length, normal, u_lo, u_hi, 0.0, dh, 0.05)
    _quad_on_edge(frame_v, frame_t, edge, length, normal, u_lo - fw, u_lo, 0.0, dh + fw, 0.09)
    _quad_on_edge(frame_v, frame_t, edge, length, normal, u_hi, u_hi + fw, 0.0, dh + fw, 0.09)
    _quad_on_edge(frame_v, frame_t, edge, length, normal, u_lo, u_hi, dh, dh + fw, 0.09)
    return (u_lo, u_hi)


# ---------------------------------------------------------------------------
# 3. glTF 2.0 binary (.glb) serialiser
# ---------------------------------------------------------------------------

_GLB_MAGIC    = 0x46546C67  # "glTF"
_GLB_VERSION  = 2
_CHUNK_JSON   = 0x4E4F534A  # "JSON"
_CHUNK_BIN    = 0x004E4942  # "BIN\0"


def _pack_f32(values: list[float]) -> bytes:
    return struct.pack(f"<{len(values)}f", *values)


def _pack_u16(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}H", *values)


def _pack_u32(values: list[int]) -> bytes:
    return struct.pack(f"<{len(values)}I", *values)


def _align4(data: bytes) -> bytes:
    pad = (4 - len(data) % 4) % 4
    return data + b"\x00" * pad


def _assemble_glb(gltf: dict[str, Any], bin_buffer: bytes) -> bytes:
    """Serialise a glTF JSON dict + binary buffer into a .glb container."""
    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    # La spec glTF exige que le chunk JSON soit padde avec des ESPACES
    # (0x20), pas des zeros : JSON.parse (three.js, validateur Khronos)
    # rejette le texte JSON suivi de \x00.
    pad = (4 - len(json_bytes) % 4) % 4
    json_chunk = json_bytes + b" " * pad

    bin_chunk_data = _align4(bin_buffer)

    json_chunk_header = struct.pack("<II", len(json_chunk), _CHUNK_JSON)
    bin_chunk_header  = struct.pack("<II", len(bin_chunk_data), _CHUNK_BIN)

    body = (
        json_chunk_header + json_chunk
        + bin_chunk_header + bin_chunk_data
    )

    total_length = 12 + len(body)
    glb_header = struct.pack("<III", _GLB_MAGIC, _GLB_VERSION, total_length)

    return glb_header + body


def _build_mesh(
    ring: list[Point2D],
    height: float,
    wall_color: list[float],  # [r, g, b] 0–1
    roof_color: list[float],
    floor_color: list[float],
) -> tuple[list[Point3D], list[tuple[int, int, int]]]:
    """
    Build a closed 3D mesh from a 2D footprint ring and a height value.

    Returns (vertices, triangles) where vertices are (x, y, z) in glTF space
    (Y = up) and triangles are index triples.

    We produce 4 groups of faces:
      - Floor (y=0, facing down)
      - Roof  (y=height, facing up)
      - Walls (lateral faces, one quad per edge)
    """
    n = len(ring)
    ring = _ensure_ccw(ring)

    vertices: list[Point3D] = []
    triangles: list[tuple[int, int, int]] = []

    # -- Floor (y = 0) --
    floor_start = len(vertices)
    for x, z in ring:
        vertices.append((x, 0.0, z))

    floor_tris = _triangulate_polygon(ring)
    for a, b, c in floor_tris:
        # Flip winding for downward-facing floor
        triangles.append((floor_start + a, floor_start + c, floor_start + b))

    # -- Roof (y = height) --
    roof_start = len(vertices)
    for x, z in ring:
        vertices.append((x, height, z))

    roof_tris = _triangulate_polygon(ring)
    for a, b, c in roof_tris:
        triangles.append((roof_start + a, roof_start + b, roof_start + c))

    # -- Walls (one quad = 2 triangles per edge) --
    for i in range(n):
        j = (i + 1) % n
        x0, z0 = ring[i]
        x1, z1 = ring[j]

        # 4 wall vertices
        v0 = len(vertices);  vertices.append((x0, 0.0,    z0))
        v1 = len(vertices);  vertices.append((x1, 0.0,    z1))
        v2 = len(vertices);  vertices.append((x1, height, z1))
        v3 = len(vertices);  vertices.append((x0, height, z0))

        triangles.append((v0, v1, v2))
        triangles.append((v0, v2, v3))

    # Winding final : le ring est exprimé en (x, z) — un parcours
    # trigonométrique dans ce plan produit une normale -y (x̂ × ẑ = -ŷ), donc
    # TOUTES les faces (sol, toit, murs) arrivent orientées vers l'intérieur
    # en convention glTF Y-up (vérifié : 0/12 faces vers l'extérieur). On
    # inverse donc le winding de chaque triangle : 12/12 vers l'extérieur,
    # et les faces sont visibles avec doubleSided=false (culling correct
    # côté three.js — sans ce fix, le bâtiment apparaissait translucide).
    triangles = [(a, c, b) for a, b, c in triangles]

    return vertices, triangles


def build_glb(
    ring: list[Point2D],
    height_m: float = 6.0,
    label: str = "Bâtiment",
    mat_mur: str | None = None,
    mat_toit: str | None = None,
) -> bytes:
    """
    Build a .glb binary from a 2D footprint ring and a height.

    Parameters
    ----------
    ring : list of (x, z) tuples in metres, local CRS centred on building.
    height_m : total building height in metres.
    label : human-readable name embedded in the glTF asset.

    Returns
    -------
    bytes — a valid glTF 2.0 Binary (.glb) file.
    """
    if not ring or len(ring) < 3:
        raise ValueError("ring must have at least 3 points")

    height_m = max(height_m, 2.5)  # safety floor: at least 2.5 m

    # Material colours (BIM-style)
    wall_color  = [0.76, 0.71, 0.65, 1.0]  # light stone
    roof_color  = [0.35, 0.33, 0.31, 1.0]  # dark grey
    floor_color = [0.60, 0.58, 0.55, 1.0]  # concrete

    vertices, triangles = _build_mesh(ring, height_m, wall_color[:3], roof_color[:3], floor_color[:3])

    # Flatten positions (x, y, z) * n_vertices
    pos_data: list[float] = []
    for x, y, z in vertices:
        pos_data.extend([x, y, z])

    # Flatten indices (u16 or u32 depending on vertex count)
    use_u32 = len(vertices) > 65535
    idx_data: list[int] = []
    for a, b, c in triangles:
        idx_data.extend([a, b, c])

    # Bounding box
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    pos_min = [min(xs), min(ys), min(zs)]
    pos_max = [max(xs), max(ys), max(zs)]

    # --- Binary buffer ---
    # Layout: [index_bytes][padding][position_bytes]
    if use_u32:
        idx_bytes = _pack_u32(idx_data)
        idx_component_type = 5125  # UNSIGNED_INT
    else:
        idx_bytes = _pack_u16(idx_data)
        idx_component_type = 5123  # UNSIGNED_SHORT

    idx_bytes_aligned = _align4(idx_bytes)
    pos_bytes = _pack_f32(pos_data)

    bin_buffer = idx_bytes_aligned + pos_bytes

    idx_byte_offset = 0
    idx_byte_length = len(idx_bytes)
    pos_byte_offset = len(idx_bytes_aligned)
    pos_byte_length = len(pos_bytes)

    n_indices  = len(idx_data)
    n_vertices = len(vertices)

    # --- glTF JSON ---
    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "Typhoon gltf_builder v1",
            "copyright": f"Typhoon — {label}",
        },
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [0]}],
        "nodes": [{"mesh": 0, "name": label}],
        "meshes": [
            {
                "name": label,
                "primitives": [
                    {
                        "attributes": {"POSITION": 1},
                        "indices": 0,
                        "material": 0,
                    }
                ],
            }
        ],
        "materials": [
            {
                "name": "Facade",
                "pbrMetallicRoughness": {
                    "baseColorFactor": wall_color,
                    "metallicFactor": 0.0,
                    "roughnessFactor": 0.85,
                },
                "doubleSided": False,
            }
        ],
        "accessors": [
            # 0 — indices
            {
                "bufferView": 0,
                "byteOffset": 0,
                "componentType": idx_component_type,
                "count": n_indices,
                "type": "SCALAR",
            },
            # 1 — positions
            {
                "bufferView": 1,
                "byteOffset": 0,
                "componentType": 5126,  # FLOAT
                "count": n_vertices,
                "type": "VEC3",
                "min": pos_min,
                "max": pos_max,
            },
        ],
        "bufferViews": [
            # 0 — indices view
            {
                "buffer": 0,
                "byteOffset": idx_byte_offset,
                "byteLength": idx_byte_length,
                "target": 34963,  # ELEMENT_ARRAY_BUFFER
            },
            # 1 — positions view
            {
                "buffer": 0,
                "byteOffset": pos_byte_offset,
                "byteLength": pos_byte_length,
                "target": 34962,  # ARRAY_BUFFER
            },
        ],
        "buffers": [
            {
                "byteLength": len(bin_buffer),
            }
        ],
    }

    return _assemble_glb(gltf, bin_buffer)


# ---------------------------------------------------------------------------
# 4. BIM builder — real footprint (polygones + trous) + slabs + pitched roof
# ---------------------------------------------------------------------------

# Palette matériaux — slug BDNB (mat_mur_txt / mat_toit_txt normalisés) -> RGB.
_MUR_COULEURS: dict[str, list[float]] = {
    "brique":      [0.72, 0.45, 0.32],
    "pierre":      [0.82, 0.78, 0.70],
    "meuliere":    [0.80, 0.74, 0.64],
    "parpaing":    [0.74, 0.72, 0.68],
    "agglomere":   [0.74, 0.72, 0.68],  # FFO "AGGLOMERE" = parpaing
    "beton":       [0.66, 0.66, 0.68],
    "bois":        [0.56, 0.42, 0.28],
    "pan_de_bois": [0.56, 0.42, 0.28],
    "torchis":     [0.72, 0.62, 0.48],
}
_TOIT_COULEURS: dict[str, list[float]] = {
    "ardoise":     [0.32, 0.32, 0.35],
    "tuile":       [0.64, 0.30, 0.20],
    "zinc":        [0.55, 0.58, 0.61],
    "bac_acier":   [0.46, 0.48, 0.51],
    "beton":       [0.56, 0.56, 0.58],
    "vegetalise":  [0.35, 0.46, 0.33],
}
_PLANCHER_COULEUR = [0.58, 0.56, 0.52]

_DEFAUT_MUR  = [0.76, 0.71, 0.65]  # pierre claire
_DEFAUT_TOIT = [0.35, 0.33, 0.31]  # gris sombre


def _couleur_slug(
    slug: str | None,
    palette: dict[str, list[float]],
    defaut: list[float],
    priorites: list[str] | None = None,
) -> list[float]:
    key = _meilleur_slug(slug, priorites if priorites is not None else list(palette.keys()))
    if key is not None and key in palette:
        return palette[key]
    return defaut


# -- Textures matériaux (fichiers seamless embarqués dans le .glb) ----------
# Même logique de correspondance par sous-chaîne que _couleur_slug. Un
# matériau sans fichier texture (absent du mapping OU fichier manquant sur
# disque) garde sa couleur unie : le rendu reste fail-soft.
_TEXTURES_DIR = Path(__file__).resolve().parent / "textures"

_MUR_TEXTURES: dict[str, str] = {
    "brique":    "mur_brique.jpg",
    "pierre":    "mur_pierre.jpg",
    "meuliere":  "mur_meuliere.jpg",
    "parpaing":  "mur_agglomere.jpg",
    "agglomere": "mur_agglomere.jpg",
    "beton":     "mur_beton.jpg",
    "bois":      "mur_bois.jpg",
}
# Variante immeuble : la pierre d'un collectif urbain est de la pierre de
# taille (appareillage lisse a joints fins, type haussmannien), pas les
# moellons ruraux de mur_pierre.jpg.
_MUR_TEXTURES_IMMEUBLE: dict[str, str] = {
    **_MUR_TEXTURES,
    "pierre": "mur_pierre_taille.jpg",
}
_TOIT_TEXTURES: dict[str, str] = {
    "tuile":    "toit_tuiles.jpg",
    "ardoise":  "toit_ardoises.jpg",
    "zinc":     "toit_zinc.jpg",
    "beton":    "toit_beton.jpg",
}
# Repli quand le matériau BDNB est INDETERMINE/AUTRES/absent : enduit neutre
# pour les murs ; pas de fichier toit_defaut pour l'instant → couleur unie.
_MUR_TEXTURE_DEFAUT = "mur_defaut.jpg"
_TOIT_TEXTURE_DEFAUT = "toit_defaut.jpg"

# Textures fixes (indépendantes de la BDNB) des autres surfaces.
_SOL_TEXTURE = "sol_herbe.jpg"
_PLANCHER_TEXTURE = "plancher_granite.jpg"
_PORTE_TEXTURE = "porte.jpg"

# Taille "monde" d'un carreau de texture, en mètres (une texture 1K seamless
# répétée tous les N mètres). Clé = nom de matériau glTF.
_TEXTURE_TILE_M: dict[str, float] = {
    "Murs": 3.0,
    "Toiture": 3.0,
    "Sol": 5.0,
    "Planchers": 2.0,
}

# Matériaux dont la texture est AJUSTÉE à la partie (une seule occurrence de
# l'image, pas de répétition) — la porte affiche l'image entière du vantail.
_TEXTURE_FIT_MATERIALS = {"Porte"}

_MIME_BY_EXT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


def _texture_file(filename: str | None) -> Path | None:
    if not filename:
        return None
    path = _TEXTURES_DIR / filename
    return path if path.is_file() else None


# Les libellés FFO/BDNB sont souvent COMPOSITES ("BRIQUES - PIERRE",
# "BETON - ZINC ALUMINIUM") : plusieurs matériaux dans un même mur/toit.
# On choisit alors le matériau qui domine l'ASPECT de la façade (parement),
# pas le premier du libellé : sur l'haussmannien "BRIQUES - PIERRE", la
# structure est en brique mais ce que l'on voit est la pierre de taille.
_MUR_PRIORITE = [
    "pierre", "meuliere", "brique", "beton",
    "agglomere", "parpaing", "pan_de_bois", "bois", "torchis",
]
_TOIT_PRIORITE = ["tuile", "ardoise", "zinc", "bac_acier", "vegetalise", "beton"]


def _meilleur_slug(label: str | None, priorites: list[str]) -> str | None:
    """Clé matériau retenue pour un libellé BDNB (composite ou non), par
    ordre de priorité visuelle. None si aucun matériau connu."""
    if not label:
        return None
    s = label.lower().replace(" ", "_").replace("-", "_")
    for key in priorites:
        if key in s:
            return key
    return None


def _texture_for_slug(
    slug: str | None,
    mapping: dict[str, str],
    defaut: str | None = None,
    priorites: list[str] | None = None,
) -> Path | None:
    """Fichier texture correspondant au libellé matériau. Sans correspondance
    (ou fichier du mapping manquant), essaie `defaut` ; None en dernier
    ressort (repli couleur unie)."""
    if slug:
        key = _meilleur_slug(slug, priorites if priorites is not None else list(mapping.keys()))
        if key is not None and key in mapping:
            return _texture_file(mapping[key]) or _texture_file(defaut)
    return _texture_file(defaut)


def _fit_uvs(vertices: list[Point3D]) -> list[tuple[float, float]]:
    """UV ajustés au rectangle englobant de la partie : u = position le long
    de l'axe horizontal dominant, v = du haut (0) vers le bas (1), convention
    glTF. Utilisé pour la porte (une occurrence entière de l'image)."""
    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    dx = max(xs) - min(xs)
    dz = max(zs) - min(zs)
    dy = (max(ys) - min(ys)) or 1.0
    horiz = xs if dx >= dz else zs
    hmin = min(horiz)
    hspan = (max(horiz) - hmin) or 1.0
    y_max = max(ys)
    return [
        ((h - hmin) / hspan, (y_max - y) / dy)
        for h, y in zip(horiz, ys)
    ]


def _planar_uvs(
    vertices: list[Point3D],
    triangles: list[tuple[int, int, int]],
    tile_m: float,
) -> list[tuple[float, float]]:
    """UV par projection planaire sur l'axe dominant de chaque face (les
    sommets ne sont pas partagés entre triangles : pas de couture à gérer).
    La projection est en coordonnées monde → la texture reste continue entre
    faces coplanaires adjacentes, et se répète tous les `tile_m` mètres."""
    uvs: list[tuple[float, float]] = [(0.0, 0.0)] * len(vertices)
    inv = 1.0 / max(tile_m, 0.1)
    for a, b, c in triangles:
        n = _tri_normal(vertices[a], vertices[b], vertices[c])
        ax, ay, az = abs(n[0]), abs(n[1]), abs(n[2])
        for i in (a, b, c):
            x, y, z = vertices[i]
            if ay >= ax and ay >= az:
                # Face horizontale (toit plat, plancher, sol) : plan XZ.
                uvs[i] = (x * inv, z * inv)
            elif ax >= az:
                # Face verticale orientée ±X : plan ZY (v = -y : le haut de
                # l'image vers le haut du mur, convention glTF v vers le bas).
                uvs[i] = (z * inv, -y * inv)
            else:
                # Face verticale orientée ±Z : plan XY.
                uvs[i] = (x * inv, -y * inv)
    return uvs


def _build_bim_parts(
    polygones: list[dict[str, Any]],
    eave_h: float,
    ridge_h: float,
    ridge_axis_deg: float,
    floors: int,
    level_h: float,
    roof_pitched: bool,
    facades_avec_vitrage: list[str] | None = None,
    ratio_vitrage: float | None = None,
    entree_facade: str | None = None,
    etages_separes: bool = False,
) -> dict[str, tuple[list[Point3D], list[tuple[int, int, int]]]]:
    """Build the mesh parts (murs ou etages, toiture, planchers) for a set of
    footprint polygons (footprint.py convention: exterieur + trous).

    `etages_separes` : quand True, la cle "murs" est remplacee par une cle
    "etage_1".."etage_N" par niveau (bandes de murs decoupees en tranches
    horizontales) — cote viewer, chaque etage devient un noeud independant
    manipurable (cisaillement sismique, effondrement).
    """
    walls_v: list[Point3D] = []
    walls_t: list[tuple[int, int, int]] = []
    roof_v: list[Point3D] = []
    roof_t: list[tuple[int, int, int]] = []
    slab_v: list[Point3D] = []
    slab_t: list[tuple[int, int, int]] = []

    def _iter_rings() -> tuple[list[Point2D], ...]:
        """(exterieur CCW, cours CW) normalises pour tous les polygones."""
        rings: list[list[Point2D]] = []
        for poly in polygones:
            ext = poly.get("exterieur") or []
            if len(ext) < 3:
                continue
            if _signed_area_2d(ext) < 0:
                ext = list(reversed(ext))
            rings.append(ext)
            for trou in poly.get("trous") or []:
                if len(trou) < 3:
                    continue
                if _signed_area_2d(trou) > 0:
                    trou = list(reversed(trou))
                rings.append(trou)
        return tuple(rings)

    # -- Walls : every polygon, exterior + courtyards (holes) --
    if etages_separes and floors > 1:
        # Une cle "etage_k" par niveau : bande [ (k-1)*level_h, min(k*level_h,
        # eave_h) ]. Le dernier niveau est ecrête par l'avant-toit.
        etages: dict[str, tuple[list[Point3D], list[tuple[int, int, int]]]] = {}
        for k in range(floors):
            y0 = k * level_h
            y1 = min((k + 1) * level_h, eave_h)
            if y1 - y0 < 0.15:
                continue
            ev: list[Point3D] = []
            et: list[tuple[int, int, int]] = []
            for ring in _iter_rings():
                _add_ring_walls_band(ev, et, ring, y0, y1)
            etages[f"etage_{k + 1}"] = (ev, et)
        walls_part: dict[str, tuple[list[Point3D], list[tuple[int, int, int]]]] = etages
    else:
        for ring in _iter_rings():
            _add_ring_walls(walls_v, walls_t, ring, eave_h)
        walls_part = {"murs": (walls_v, walls_t)}

    # -- Roof --
    if roof_pitched and ridge_h > eave_h + 0.05:
        # Deux pans le long de l'axe dominant : chaque arête du polygone
        # produit un pan incliné montant jusqu'au faîtage (le sommet projeté
        # sur l'axe du faîtage, à hauteur ridge_h).
        ax = math.cos(math.radians(ridge_axis_deg))
        az = math.sin(math.radians(ridge_axis_deg))
        for poly in polygones:
            ext = poly.get("exterieur") or []
            if len(ext) < 3:
                continue
            cx = sum(p[0] for p in ext) / len(ext)
            cz = sum(p[1] for p in ext) / len(ext)
            n = len(ext)
            for i in range(n):
                x0, z0 = ext[i]
                x1, z1 = ext[(i + 1) % n]
                if math.hypot(x1 - x0, z1 - z0) < 1e-9:
                    continue
                # Projection des sommets sur l'axe du faîtage.
                t0 = (x0 - cx) * ax + (z0 - cz) * az
                t1 = (x1 - cx) * ax + (z1 - cz) * az
                rx0, rz0 = cx + t0 * ax, cz + t0 * az
                rx1, rz1 = cx + t1 * ax, cz + t1 * az
                a = (x0, eave_h, z0)
                b = (x1, eave_h, z1)
                c = (rx1, ridge_h, rz1)
                d = (rx0, ridge_h, rz0)
                _push_quad(roof_v, roof_t, a, b, c, d, (0.0, 1.0, 0.0))
    else:
        # Toit plat : dalle triangulée (avec trous) à hauteur ridge_h.
        for poly in polygones:
            ext = poly.get("exterieur") or []
            if len(ext) < 3:
                continue
            ring, tris = _triangulate_polygon_with_holes(ext, poly.get("trous") or [])
            base = len(roof_v)
            for a, b, c in tris:
                roof_v.append((ring[a][0], ridge_h, ring[a][1]))
                roof_v.append((ring[b][0], ridge_h, ring[b][1]))
                roof_v.append((ring[c][0], ridge_h, ring[c][1]))
                roof_t.append((base, base + 1, base + 2))
                base += 3

    # -- Floor slabs : un plancher par niveau (visible en coupe) --
    # Bornés sous l'avant-toit : le dernier plancher ne doit pas dépasser
    # les murs (sous un toit pentu, eave_h < hauteur).
    y_max = eave_h - 0.15
    for k in range(floors):
        # 3 cm au-dessus de y=0 pour la dalle du RDC : évite le z-fighting
        # avec le sol du .glb (-5 cm) ET le plan d'herbe du viewer (y=0).
        y = max(min(k * level_h, y_max), 0.03)
        for poly in polygones:
            ext = poly.get("exterieur") or []
            if len(ext) < 3:
                continue
            ring, tris = _triangulate_polygon_with_holes(ext, poly.get("trous") or [])
            base = len(slab_v)
            for a, b, c in tris:
                slab_v.append((ring[a][0], y, ring[a][1]))
                slab_v.append((ring[b][0], y, ring[b][1]))
                slab_v.append((ring[c][0], y, ring[c][1]))
                slab_t.append((base, base + 1, base + 2))
                base += 3

    # -- Fenetres (facades vitrees du DPE) + porte d'entree (facade rue) --
    glass_v: list[Point3D] = []
    glass_t: list[tuple[int, int, int]] = []
    frame_v: list[Point3D] = []
    frame_t: list[tuple[int, int, int]] = []
    door_v: list[Point3D] = []
    door_t: list[tuple[int, int, int]] = []

    edges = _iter_exterior_edges(polygones)
    glazed: set[str] = set()
    for f in facades_avec_vitrage or []:
        o = str(f).lower().replace("murs_", "").strip()
        if o in _ORIENTATIONS:
            glazed.add(o)

    # La porte d'abord : on connait ainsi l'intervalle d'abscisse a eviter
    # pour les fenetres du rez-de-chaussee du meme mur. Elle est INDEPENDANTE
    # du vitrage (la couverture DPE est partielle : un batiment sans donnees
    # de baies vitrees garde sa porte cote rue).
    door_zone: tuple[float, float] | None = None
    door_edge_ref = None
    entree_o = str(entree_facade or "").lower().replace("murs_", "").strip()
    if entree_o in _ORIENTATIONS:
        best = None
        best_len = 0.0
        for e in edges:
            if e[2] > best_len and _facade_orientation(e[3][0], e[3][1]) == entree_o:
                best, best_len = e, e[2]
        if best is not None:
            door_edge_ref = best
            door_zone = _add_door(
                (door_v, door_t), (frame_v, frame_t),
                (best[0], best[1]), best[2], best[3],
            )

    if glazed and ratio_vitrage:
        for e in edges:
            if _facade_orientation(e[3][0], e[3][1]) not in glazed:
                continue
            zone = door_zone if e is door_edge_ref else None
            _add_windows(
                (glass_v, glass_t), (frame_v, frame_t),
                (e[0], e[1]), e[2], e[3],
                eave_h, floors, level_h, ratio_vitrage, zone,
            )

    return {
        **walls_part,
        "toiture": (roof_v, roof_t),
        "planchers": (slab_v, slab_t),
        "cadres": (frame_v, frame_t),
        "vitrage": (glass_v, glass_t),
        "porte": (door_v, door_t),
    }


def _serialise_parts_glb(
    parts: dict[str, tuple[list[Point3D], list[tuple[int, int, int]]]],
    materials: list[dict[str, Any]],
    label: str,
    parts_as_nodes: bool = False,
) -> bytes:
    """Serialise several named mesh parts into a .glb.

    Default : UNE mesh avec une primitive par partie (une seule node).
    `parts_as_nodes=True` : chaque partie devient sa propre node + sa propre
    mesh (nommee d'apres la partie) — le viewer peut alors deplacer chaque
    etage independamment (simulation sismique / effondrement).
    """
    primitives: list[dict[str, Any]] = []
    accessors: list[dict[str, Any]] = []
    buffer_views: list[dict[str, Any]] = []
    bin_parts: list[bytes] = []
    # En mode nodes : une mesh par partie (son primitive unique) + son node.
    per_part_primitive: dict[str, dict[str, Any]] = {}

    # On n'emet que les parties qui ont de la geometrie, et uniquement LEURS
    # materiaux : un batiment sans fenetres ne transporte pas de material
    # "Vitrage" inutilise (le viewer et le contrat restent propres).
    #
    # NB : le materiau est associe par NOM de partie (pas par position dans
    # `parts`) : avec `etages_separes`, il y a plus de parties (etage_1..N)
    # que de materiaux — les etages partagent le materiau "Murs" (index 0).
    part_names = list(parts.keys())
    used = [name for name in part_names if parts[name][1]]

    _MATERIAL_BY_PART = {
        "murs": 0,
        "toiture": 1,
        "planchers": 2,
        "cadres": 3,
        "vitrage": 4,
        "porte": 5,
        "sol": 6,
    }
    used_mat_ids: list[int] = []
    for name in used:
        mid = _MATERIAL_BY_PART.get(name, 0)  # etage_N -> Murs
        if mid not in used_mat_ids:
            used_mat_ids.append(mid)
    mat_index = {mid: new for new, mid in enumerate(used_mat_ids)}
    materials = [materials[mid] for mid in used_mat_ids]

    byte_cursor = 0
    for name in used:
        vertices, triangles = parts[name]
        mid = _MATERIAL_BY_PART.get(name, 0)
        use_u32 = len(vertices) > 65535
        idx_data: list[int] = []
        for a, b, c in triangles:
            idx_data.extend([a, b, c])

        if use_u32:
            idx_bytes = _pack_u32(idx_data)
            idx_component_type = 5125
        else:
            idx_bytes = _pack_u16(idx_data)
            idx_component_type = 5123

        idx_bytes_aligned = _align4(idx_bytes)

        pos_data: list[float] = []
        for x, y, z in vertices:
            pos_data.extend([x, y, z])
        pos_bytes = _pack_f32(pos_data)

        xs = [v[0] for v in vertices]
        ys = [v[1] for v in vertices]
        zs = [v[2] for v in vertices]
        pos_min = [min(xs), min(ys), min(zs)]
        pos_max = [max(xs), max(ys), max(zs)]

        # views (indices, then positions) appended to the shared buffer
        buffer_views.append({
            "buffer": 0,
            "byteOffset": byte_cursor,
            "byteLength": len(idx_bytes),
            "target": 34963,  # ELEMENT_ARRAY_BUFFER
        })
        byte_cursor += len(idx_bytes_aligned)

        buffer_views.append({
            "buffer": 0,
            "byteOffset": byte_cursor,
            "byteLength": len(pos_bytes),
            "target": 34962,  # ARRAY_BUFFER
        })
        byte_cursor += len(pos_bytes)

        bin_parts.append(idx_bytes_aligned)
        bin_parts.append(pos_bytes)

        acc_base = len(accessors)
        accessors.append({
            "bufferView": len(buffer_views) - 2,
            "byteOffset": 0,
            "componentType": idx_component_type,
            "count": len(idx_data),
            "type": "SCALAR",
        })
        accessors.append({
            "bufferView": len(buffer_views) - 1,
            "byteOffset": 0,
            "componentType": 5126,
            "count": len(vertices),
            "type": "VEC3",
            "min": pos_min,
            "max": pos_max,
        })

        attributes: dict[str, int] = {"POSITION": acc_base + 1}

        # -- TEXCOORD_0 : seulement pour les parties dont le matériau porte
        # une texture (UV planaires monde, cf. _planar_uvs).
        mat_def = materials[mat_index[mid]]
        if "_texture" in mat_def and vertices:
            if mat_def.get("name") in _TEXTURE_FIT_MATERIALS:
                uvs = _fit_uvs(vertices)
            else:
                tile_m = _TEXTURE_TILE_M.get(mat_def.get("name", ""), 3.0)
                uvs = _planar_uvs(vertices, triangles, tile_m)
            uv_data: list[float] = []
            for u, v in uvs:
                uv_data.extend([u, v])
            uv_bytes = _pack_f32(uv_data)
            buffer_views.append({
                "buffer": 0,
                "byteOffset": byte_cursor,
                "byteLength": len(uv_bytes),
                "target": 34962,  # ARRAY_BUFFER
            })
            byte_cursor += len(uv_bytes)
            bin_parts.append(uv_bytes)
            accessors.append({
                "bufferView": len(buffer_views) - 1,
                "byteOffset": 0,
                "componentType": 5126,
                "count": len(vertices),
                "type": "VEC2",
            })
            attributes["TEXCOORD_0"] = len(accessors) - 1

        primitive = {
            "attributes": attributes,
            "indices": acc_base,
            "material": mat_index[mid],
        }
        primitives.append(primitive)
        per_part_primitive[name] = primitive

    # -- Textures : embarquer chaque image (une fois) dans le buffer binaire,
    # brancher baseColorTexture, retirer la clé privée "_texture".
    images: list[dict[str, Any]] = []
    textures: list[dict[str, Any]] = []
    samplers: list[dict[str, Any]] = []
    texture_index_by_path: dict[str, int] = {}
    for mat_def in materials:
        tex_path = mat_def.pop("_texture", None)
        if tex_path is None:
            continue
        key = str(tex_path)
        if key not in texture_index_by_path:
            try:
                img_bytes = Path(tex_path).read_bytes()
            except OSError:
                continue  # fichier illisible → repli couleur unie
            if not samplers:
                samplers.append({
                    "magFilter": 9729,  # LINEAR
                    "minFilter": 9987,  # LINEAR_MIPMAP_LINEAR
                    "wrapS": 10497,     # REPEAT
                    "wrapT": 10497,     # REPEAT
                })
            img_aligned = _align4(img_bytes)
            buffer_views.append({
                "buffer": 0,
                "byteOffset": byte_cursor,
                "byteLength": len(img_bytes),
            })
            byte_cursor += len(img_aligned)
            bin_parts.append(img_aligned)
            images.append({
                "bufferView": len(buffer_views) - 1,
                "mimeType": _MIME_BY_EXT.get(Path(tex_path).suffix.lower(), "image/jpeg"),
                "name": Path(tex_path).stem,
            })
            textures.append({"sampler": 0, "source": len(images) - 1})
            texture_index_by_path[key] = len(textures) - 1
        mat_def["pbrMetallicRoughness"]["baseColorTexture"] = {
            "index": texture_index_by_path[key]
        }

    bin_buffer = b"".join(bin_parts)

    if parts_as_nodes and len(used) > 1:
        # Chaque partie -> node nommee + mesh a un seul primitive.
        nodes = [
            {"mesh": i, "name": _PART_NODE_LABEL.get(name, name)}
            for i, name in enumerate(used)
        ]
        meshes = [
            {
                "name": _PART_NODE_LABEL.get(name, name),
                "primitives": [per_part_primitive[name]],
            }
            for name in used
        ]
    else:
        nodes = [{"mesh": 0, "name": label}]
        meshes = [{"name": label, "primitives": primitives}]

    gltf = {
        "asset": {
            "version": "2.0",
            "generator": "Typhoon gltf_builder v2.1 (BIM)",
            "copyright": f"Typhoon — {label}",
        },
        "scene": 0,
        "scenes": [{"name": "Scene", "nodes": [i for i in range(len(nodes))]}],
        "nodes": nodes,
        "meshes": meshes,
        "materials": materials,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(bin_buffer)}],
    }
    if textures:
        gltf["samplers"] = samplers
        gltf["images"] = images
        gltf["textures"] = textures

    return _assemble_glb(gltf, bin_buffer)



# Libelle lisible des noeuds glTF (BimTree / selection) : les cles internes
# "etage_1" deviennent "Étage 1", etc. — le viewer s'appuie sur le prefixe
# "Etage " (sans accent) pour decouper la structure par niveau.
_PART_NODE_LABEL = {
    "toiture": "Toiture",
    "planchers": "Planchers",
    "cadres": "Cadres",
    "vitrage": "Vitrage",
    "porte": "Porte",
    "murs": "Murs",
    **{f"etage_{k}": f"Etage {k}" for k in range(1, 10)},
}


def _materials_for(
    mat_mur: str | None, mat_toit: str | None, immeuble: bool = False
) -> list[dict[str, Any]]:
    mur = _couleur_slug(mat_mur, _MUR_COULEURS, _DEFAUT_MUR, _MUR_PRIORITE)
    toit = _couleur_slug(mat_toit, _TOIT_COULEURS, _DEFAUT_TOIT, _TOIT_PRIORITE)

    # Texture selon le matériau BDNB. Quand une texture existe, la couleur de
    # base passe au blanc (le facteur MULTIPLIE la texture en glTF : garder la
    # couleur palette assombrirait/teinterait l'image). La clé privée
    # "_texture" est consommée puis retirée par _serialise_parts_glb.
    murs_mat: dict[str, Any] = {
        "name": "Murs",
        "pbrMetallicRoughness": {
            "baseColorFactor": mur + [1.0],
            "metallicFactor": 0.0,
            "roughnessFactor": 0.9,
        },
        "doubleSided": False,
    }
    tex_mur = _texture_for_slug(
        mat_mur,
        _MUR_TEXTURES_IMMEUBLE if immeuble else _MUR_TEXTURES,
        _MUR_TEXTURE_DEFAUT,
        _MUR_PRIORITE,
    )
    if tex_mur is not None:
        murs_mat["_texture"] = tex_mur
        murs_mat["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]

    toit_mat: dict[str, Any] = {
        "name": "Toiture",
        "pbrMetallicRoughness": {
            "baseColorFactor": toit + [1.0],
            "metallicFactor": 0.0,
            "roughnessFactor": 0.8,
        },
        "doubleSided": True,
    }
    tex_toit = _texture_for_slug(mat_toit, _TOIT_TEXTURES, _TOIT_TEXTURE_DEFAUT, _TOIT_PRIORITE)
    if tex_toit is not None:
        toit_mat["_texture"] = tex_toit
        toit_mat["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]

    mats: list[dict[str, Any]] = [
        murs_mat,
        toit_mat,
        {
            "name": "Planchers",
            "pbrMetallicRoughness": {
                "baseColorFactor": _PLANCHER_COULEUR + [1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.85,
            },
            "doubleSided": True,
        },
        {
            "name": "Cadres",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.92, 0.93, 0.95, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.35,
            },
            "doubleSided": True,
        },
        {
            "name": "Vitrage",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.45, 0.62, 0.72, 0.5],
                "metallicFactor": 0.9,
                "roughnessFactor": 0.05,
            },
            "doubleSided": True,
            "alphaMode": "BLEND",
        },
        {
            "name": "Porte",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.42, 0.28, 0.17, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 0.7,
            },
            "doubleSided": False,
        },
        {
            "name": "Sol",
            "pbrMetallicRoughness": {
                "baseColorFactor": [0.36, 0.45, 0.30, 1.0],
                "metallicFactor": 0.0,
                "roughnessFactor": 1.0,
            },
            "doubleSided": True,
        },
    ]

    # Textures fixes (indépendantes de la BDNB) : sol, planchers, porte.
    # Même contrat fail-soft : fichier absent → couleur unie conservée.
    statiques = {"Sol": _SOL_TEXTURE, "Planchers": _PLANCHER_TEXTURE, "Porte": _PORTE_TEXTURE}
    for mat_def in mats:
        filename = statiques.get(mat_def["name"])
        tex = _texture_file(filename) if filename else None
        if tex is not None:
            mat_def["_texture"] = tex
            mat_def["pbrMetallicRoughness"]["baseColorFactor"] = [1.0, 1.0, 1.0, 1.0]

    return mats


def build_glb_bim(
    polygones: list[dict[str, Any]],
    hauteur_m: float = 6.0,
    label: str = "Bâtiment",
    mat_mur: str | None = None,
    mat_toit: str | None = None,
    floors: int | None = None,
    pente_toit_deg: float | None = None,
    ridge_axis_deg: float | None = None,
    facades_avec_vitrage: list[str] | None = None,
    ratio_vitrage: float | None = None,
    entree_facade: str | None = None,

    immeuble: bool = False,

    etages_separes: bool = False,
    parts_as_nodes: bool = False,

) -> bytes:
    """
    Build a BIM-grade .glb from footprint polygons (footprint.py convention:
    list of {"exterieur": [[x,z],...], "trous": [[[...]...]...]}, metres in
    the scene frame).

    Structure : murs (tous les polygones + cours intérieures) ou etages
    (`etages_separes` : une bande de murs par niveau), planchers par niveau
    (`floors`), toit deux pans (`pente_toit_deg`, `ridge_axis_deg`) ou plat.
    Les materiaux (Murs / Toiture / Planchers) sont colores depuis les
    libelles BDNB.

    `parts_as_nodes` : quand True, chaque partie devient un noeud glTF
    independant (murs/etages, toiture, planchers, vitrage...) — requis pour
    la simulation sismique cote viewer (cisaillement / effondrement par
    etage).
    """
    if not polygones:
        raise ValueError("polygones must not be empty")

    hauteur_m = max(float(hauteur_m), 2.5)

    # -- Étages / hauteur de niveau --
    if not floors or floors < 1:
        floors = max(1, round(hauteur_m / 2.7))
    floors = min(max(int(floors), 1), 30)
    level_h = min(max(hauteur_m / floors, 2.2), 3.4)

    # -- Toiture : pente + axe du faîtage --
    pente = pente_toit_deg if pente_toit_deg is not None else 35.0
    pente = min(max(float(pente), 0.0), 60.0)
    roof_pitched = pente > 1.0

    if ridge_axis_deg is None:
        ext = (polygones[0] or {}).get("exterieur") or []
        if len(ext) >= 4:
            from app.digital_twin.footprint import dominant_axis_deg
            ridge_axis_deg = dominant_axis_deg(ext)
        else:
            ridge_axis_deg = 0.0
    ridge_axis_deg = float(ridge_axis_deg)

    # Hauteur du faîtage = hauteur du bâtiment (hauteur_mean). L'avant-toit
    # (haut des murs) est déduit de la montée : ridge - montee, borné à
    # [0.45, 0.95] × hauteur pour garder des murs visibles.
    if roof_pitched:
        ax = math.cos(math.radians(ridge_axis_deg))
        az = math.sin(math.radians(ridge_axis_deg))
        principal = max(
            polygones, key=lambda p: abs(_signed_area_2d(p.get("exterieur") or []))
        )
        ext_p = principal.get("exterieur") or []
        if ext_p:
            cx = sum(p[0] for p in ext_p) / len(ext_p)
            cz = sum(p[1] for p in ext_p) / len(ext_p)
            perp_x, perp_z = -az, ax
            demi_larg = max(
                abs((x - cx) * perp_x + (z - cz) * perp_z) for x, z in ext_p
            )
        else:
            demi_larg = 1.0
        montee = min(demi_larg * math.tan(math.radians(pente)), hauteur_m * 0.55)
        ridge_h = hauteur_m
        eave_h = max(ridge_h - montee, hauteur_m * 0.45)
    else:
        # Toit plat (terrasse) : les murs montent jusqu'a la dalle de toiture.
        # (L'ancien eave_h = floors × level_h laissait la dalle flotter au
        # dessus des murs des que la hauteur BDNB depassait ~20 m.)
        ridge_h = hauteur_m
        eave_h = hauteur_m

    parts = _build_bim_parts(
        polygones, eave_h, ridge_h, ridge_axis_deg, floors, level_h, roof_pitched,
        facades_avec_vitrage, ratio_vitrage, entree_facade,
        etages_separes=etages_separes,
    )

    # -- Sol : plan d'assise sous le bâtiment (contexte visuel, évite la
    # maison "flottante" dans le viewer). Légèrement sous y=0 pour ne pas
    # z-fighter avec la dalle du rez-de-chaussée.
    all_pts = [pt for poly in polygones for pt in (poly.get("exterieur") or [])]
    if all_pts:
        xs = [p[0] for p in all_pts]
        zs = [p[1] for p in all_pts]
        marge = max(12.0, 0.6 * max(max(xs) - min(xs), max(zs) - min(zs)))
        x0, x1 = min(xs) - marge, max(xs) + marge
        z0, z1 = min(zs) - marge, max(zs) + marge
        y_sol = -0.05
        sol_v: list[Point3D] = []
        sol_t: list[tuple[int, int, int]] = []
        _push_quad(
            sol_v, sol_t,
            (x0, y_sol, z0), (x1, y_sol, z0), (x1, y_sol, z1), (x0, y_sol, z1),
            (0.0, 1.0, 0.0),
        )
        parts["sol"] = (sol_v, sol_t)

    materials = _materials_for(mat_mur, mat_toit, immeuble=immeuble)

    return _serialise_parts_glb(parts, materials, label, parts_as_nodes=parts_as_nodes)


# ---------------------------------------------------------------------------
# 5. High-level entry point (called from the API route)
# ---------------------------------------------------------------------------

def build_glb_from_bdnb(
    batiment: dict[str, Any],
    adresse_label: str = "Bâtiment",
    adresse_lat: float | None = None,
    adresse_lon: float | None = None,
) -> bytes | None:
    """
    Build a .glb binary from a BDNB `batiment_groupe_complet` dict.

    Returns None if the batiment dict is empty or has no usable geometry.

    Parameters
    ----------
    batiment : dict from BDNB (field batiment inside bdnb response)
    adresse_label : address string to embed in glTF metadata
    adresse_lat / adresse_lon : point d'adresse geocode (WGS84) — sert a
        estimer la facade cote rue pour poser la porte d'entree
        (`footprint.estimate_street_facing_zone`). Optionnels : sans eux,
        pas de porte, mais les fenetres (DPE) restent posees.

    Returns
    -------
    bytes (.glb) or None if data is insufficient.
    """
    from app.digital_twin.footprint import extract_footprint  # avoid circular at module level

    if not batiment:
        return None

    geom_groupe = batiment.get("geom_groupe")
    hauteur_mean = batiment.get("hauteur_mean") or 6.0
    mat_mur = batiment.get("mat_mur_txt")
    mat_toit = batiment.get("mat_toit_txt")
    nb_niveau = batiment.get("nb_niveau")

    # -- Fenetres : facades vitrees + ratio de surface (DPE BDNB) --
    facades_vitrage: list[str] = []
    ratio_vitrage: float | None = None
    orients = batiment.get("l_orientation_baie_vitree")
    if isinstance(orients, list):
        for mot in orients:
            if isinstance(mot, str) and mot.strip().lower() in {"nord", "sud", "est", "ouest"}:
                facades_vitrage.append("murs_" + mot.strip().lower())
    ratio_raw = batiment.get("pourcentage_surface_baie_vitree_exterieur")
    if isinstance(ratio_raw, (int, float)) and ratio_raw > 0:
        ratio_vitrage = float(ratio_raw)
        if ratio_vitrage > 1.0:  # champ BDNB exprime en pourcentage (0-100)
            ratio_vitrage /= 100.0
    if not facades_vitrage or not ratio_vitrage:
        facades_vitrage, ratio_vitrage = [], None

    # -- Porte d'entree : facade la plus proche du point d'adresse geocode --
    entree_facade: str | None = None
    if geom_groupe and adresse_lat is not None and adresse_lon is not None:
        try:
            from app.digital_twin.footprint import estimate_street_facing_zone
            entree_facade = estimate_street_facing_zone(geom_groupe, adresse_lat, adresse_lon)
        except Exception:
            entree_facade = None

    # Try to get footprint from real BDNB geometry
    footprint_data = None
    if geom_groupe:
        try:
            footprint_data = extract_footprint(geom_groupe)
        except Exception:
            footprint_data = None

    if footprint_data and footprint_data.get("polygones"):
        polygones = footprint_data["polygones"]
        # Pente du toit déduite du matériau (ardoises 42°, tuiles 33°, zinc 15°…)
        pente_toit: float | None = None
        try:
            from app.digital_twin.geometry_builder import (
                _pente_from_materiau_toiture,
                _slugify,
            )
            pente_toit = _pente_from_materiau_toiture(_slugify(mat_toit))
        except Exception:
            pente_toit = 35.0

        # Toit deux pans seulement pour une maison basse à l'emprise
        # ~rectangulaire. Sur un immeuble collectif ou une emprise en
        # L/T/U/multipolygone, le faîtage unique projeté sur l'axe dominant
        # produit des pans absurdes : on force la toiture-terrasse (le
        # standard du bâti collectif).
        forme = footprint_data.get("forme") or ""
        rectangularite = footprint_data.get("rectangularite") or 0.0
        surface_emprise = footprint_data.get("surface_m2") or 0.0
        a_trous = any(p.get("trous") for p in polygones)
        immeuble = (
            isinstance(nb_niveau, (int, float)) and nb_niveau >= 4
        ) or float(hauteur_mean) >= 12.0
        emprise_complexe = (
            (forme and forme != "rectangulaire")
            or rectangularite < 0.80
            or len(polygones) > 1
            or a_trous
            or surface_emprise > 400.0
        )
        if immeuble or emprise_complexe:
            pente_toit = 0.0

        return build_glb_bim(
            polygones=polygones,
            hauteur_m=float(hauteur_mean),
            label=adresse_label,
            mat_mur=mat_mur,
            mat_toit=mat_toit,
            floors=nb_niveau,
            pente_toit_deg=pente_toit,
            facades_avec_vitrage=facades_vitrage,
            ratio_vitrage=ratio_vitrage,
            entree_facade=entree_facade,

            immeuble=immeuble,

            # Découpe par étage + une node par partie : la simulation sismique
            # du viewer peut cisailer/effondrer chaque niveau indépendamment.
            etages_separes=True,
            parts_as_nodes=True,

        )

    # Fallback: build a simple rectangle from surface_emprise_sol
    surface = batiment.get("surface_emprise_sol") or batiment.get("s_geom_groupe") or 100.0
    side = math.sqrt(float(surface))
    half = side / 2.0
    ring = [(-half, -half), (half, -half), (half, half), (-half, half)]

    if len(ring) < 3:
        # Ultimate fallback: 10×10 m square
        ring = [(-5.0, -5.0), (5.0, -5.0), (5.0, 5.0), (-5.0, 5.0)]

    try:
        return build_glb(
            ring=ring,
            height_m=float(hauteur_mean),
            label=adresse_label,
            mat_mur=mat_mur,
            mat_toit=mat_toit,
        )
    except Exception:
        return None
