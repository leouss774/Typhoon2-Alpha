"""digital_twin_agent — partie déterministe.

Traduit un enregistrement BDNB en bloc `geometry` du contrat de sortie.
"""

from __future__ import annotations

import math
from typing import Any, TypedDict

Point = tuple[float, float]


def _convex_hull(points: list[Point]) -> list[Point]:
    pts = sorted(set(points))
    if len(pts) <= 2:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)

    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def _min_area_rect(hull: list[Point]) -> tuple[float, float, float]:
    n = len(hull)
    if n < 3:
        return (0.0, 0.0, 0.0)

    best_area = math.inf
    best = (0.0, 0.0, 0.0)

    for i in range(n):
        ax, ay = hull[i]
        bx, by = hull[(i + 1) % n]
        edge_angle = math.atan2(by - ay, bx - ax)
        cos_a, sin_a = math.cos(-edge_angle), math.sin(-edge_angle)

        xs = [px * cos_a - py * sin_a for px, py in hull]
        ys = [px * sin_a + py * cos_a for px, py in hull]
        width = max(xs) - min(xs)
        height = max(ys) - min(ys)
        area = width * height

        if area < best_area:
            best_area = area
            long_side_angle_deg = math.degrees(edge_angle)
            if height > width:
                long_side_angle_deg += 90.0
            best = (min(width, height), max(width, height), long_side_angle_deg % 180.0)

    return best


def _extract_polygon_points(geom_groupe: dict[str, Any] | None) -> list[Point]:
    if not geom_groupe:
        return []
    coords = geom_groupe.get("coordinates")
    if not coords:
        return []
    geom_type = geom_groupe.get("type", "Polygon")
    points: list[Point] = []
    if geom_type == "MultiPolygon":
        for polygon in coords:
            ring = polygon[0]
            points.extend((float(x), float(y)) for x, y in ring)
    elif geom_type == "Polygon":
        ring = coords[0]
        points.extend((float(x), float(y)) for x, y in ring)
    return points


def bounding_rect_from_geom_groupe(geom_groupe: dict[str, Any] | None) -> tuple[float, float, float] | None:
    points = _extract_polygon_points(geom_groupe)
    if len(points) < 3:
        return None
    hull = _convex_hull(points)
    largeur, longueur, angle_from_east = _min_area_rect(hull)
    if largeur <= 0 or longueur <= 0:
        return None
    bearing = (90.0 - angle_from_east) % 90.0
    return (round(largeur, 2), round(longueur, 2), round(bearing, 1))


class GeometryResult(TypedDict):
    geometry: dict[str, Any]
    champs_manquants: list[str]
    champs_ok: list[str]


_CHAMPS_A_COMPLETER = ["has_basement", "has_cellar", "has_garage", "has_garden"]


def build_geometry_from_bdnb(
    batiment: dict[str, Any],
    formulaire: dict[str, Any] | None = None,
) -> GeometryResult:
    """Construit le bloc `geometry` du contrat digital_twin."""
    formulaire = formulaire or {}
    champs_manquants: list[str] = []
    champs_ok: list[str] = []

    rect = bounding_rect_from_geom_groupe(batiment.get("geom_groupe"))
    if formulaire.get("largeur_m") and formulaire.get("longueur_m"):
        largeur_m = formulaire["largeur_m"]
        longueur_m = formulaire["longueur_m"]
        orientation_deg = formulaire.get("orientation_deg", 0.0)
        champs_ok += ["largeur_m", "longueur_m", "orientation_deg"]
    elif rect is not None:
        largeur_m, longueur_m, orientation_deg = rect
        champs_ok += ["largeur_m", "longueur_m", "orientation_deg"]
    else:
        surface = batiment.get("surface_emprise_sol") or batiment.get("s_geom_groupe")
        side = round(math.sqrt(surface), 2) if surface else 8.0
        largeur_m, longueur_m, orientation_deg = side, side, 0.0
        champs_manquants.append("orientation_deg")

    floors_count = int(batiment.get("nb_niveau", 1))
    hauteur_sous_plafond_m = 2.7
    champs_ok += ["floors_count", "hauteur_sous_plafond_m"]

    materiau_mur = formulaire.get("materiau_mur")
    materiau_toiture = formulaire.get("materiau_toiture")

    geometry: dict[str, Any] = {
        "footprint_shape": formulaire.get("footprint_shape", "rectangulaire"),
        "largeur_m": largeur_m,
        "longueur_m": longueur_m,
        "orientation_deg": orientation_deg,
        "floors_count": floors_count,
        "hauteur_sous_plafond_m": hauteur_sous_plafond_m,
        "roof_shape": formulaire.get("roof_shape", "deux_pans"),
        "pente_toit_deg": formulaire.get("pente_toit_deg", 35.0),
        "materiau_mur": materiau_mur,
        "materiau_toiture": materiau_toiture,
    }

    for champ in _CHAMPS_A_COMPLETER:
        if champ in formulaire:
            geometry[champ] = formulaire[champ]
            champs_ok.append(champ)
        else:
            geometry[champ] = None
            champs_manquants.append(champ)

    return {
        "geometry": geometry,
        "champs_manquants": champs_manquants,
        "champs_ok": champs_ok,
    }
