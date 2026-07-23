"""
geometry_service.py
--------------------
Transforme la géométrie brute du bâtiment (`geom_groupe`, issue de la BDNB,
en Lambert-93 / EPSG:2154) en dimensions réelles exploitables par le jumeau
numérique 3D : largeur, profondeur, orientation, surface au sol, ratio.

Ce module est INDÉPENDANT du reste (Mistral, FastAPI, etc.) : il ne prend
qu'un dict GeoJSON-like en entrée et retourne un dict de nombres. Il est donc
testable seul avec `python -m backend.services.geometry_service`.

Contrat d'entrée (tel que fourni par la BDNB / merged_input.json) :
{
  "type": "MultiPolygon",
  "coordinates": [[[[x1, y1], [x2, y2], ...]]]
}
ou
{
  "type": "Polygon",
  "coordinates": [[[x1, y1], [x2, y2], ...]]
}

Contrat de sortie :
{
  "largeur_m": float,       # dimension X du rectangle englobant orienté
  "profondeur_m": float,    # dimension Z du rectangle englobant orienté
  "orientation_deg": float, # angle du bâtiment / Nord géographique (0-180°)
  "surface_sol_m2": float,  # surface réelle de l'empreinte (aire du polygone)
  "surface_rectangle_m2": float,
  "compacite": float,       # surface_sol / surface_rectangle (0-1, 1 = rectangle parfait)
  "centroid": {"x": float, "y": float},
}
"""

from __future__ import annotations

import math
from typing import Any

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry

# Bornes de sécurité pour l'affichage 3D : on ne veut jamais une maison de
# 2m ou de 80m de large à l'écran même si la donnée brute est aberrante
# (bâtiment mitoyen mal découpé, multi-polygone incluant une dépendance, etc.)
MIN_DIM_M = 4.0
MAX_DIM_M = 20.0


class GeometryError(ValueError):
    """Levée quand geom_groupe est absent, vide ou géométriquement invalide."""


def _to_shapely(geom_groupe: dict[str, Any]) -> BaseGeometry:
    if not geom_groupe or "type" not in geom_groupe or "coordinates" not in geom_groupe:
        raise GeometryError("geom_groupe manquant ou mal formé (type/coordinates requis)")
    try:
        geom = shape(geom_groupe)
    except Exception as exc:  # shapely lève des erreurs variées selon le cas
        raise GeometryError(f"geom_groupe illisible par shapely : {exc}") from exc
    if geom.is_empty:
        raise GeometryError("geom_groupe est une géométrie vide")
    if not geom.is_valid:
        geom = geom.buffer(0)  # correction standard shapely pour les polygones auto-intersectants
    return geom


def _clamp(value: float, lo: float = MIN_DIM_M, hi: float = MAX_DIM_M) -> float:
    return max(lo, min(hi, value))


def compute_house_footprint(geom_groupe: dict[str, Any]) -> dict[str, Any]:
    """
    Calcule largeur/profondeur/orientation réelles à partir de l'empreinte au sol.

    On utilise le rectangle englobant orienté minimal (minimum_rotated_rectangle)
    plutôt que le simple bounding box aligné nord-sud : un bâtiment n'est presque
    jamais parfaitement aligné sur les axes X/Y du repère Lambert-93, et prendre
    le bbox aligné donnerait une "fausse" largeur toujours plus grande que la
    réalité pour une maison en biais.
    """
    geom = _to_shapely(geom_groupe)

    # Si multipolygone (ex: maison + dépendance), on prend l'enveloppe convexe
    # de l'ensemble : on modélise ici le "groupe" bâti comme un seul volume,
    # ce qui correspond à l'usage du jumeau (une seule maison affichée).
    working_geom = geom.convex_hull if geom.geom_type != "Polygon" else geom

    mrr = working_geom.minimum_rotated_rectangle
    coords = list(mrr.exterior.coords)[:-1]  # le dernier point ferme le polygone (= premier)

    if len(coords) < 4:
        # Cas dégénéré (géométrie quasi-linéaire) : fallback sur le bbox classique
        minx, miny, maxx, maxy = working_geom.bounds
        largeur_brut = maxx - minx
        profondeur_brut = maxy - miny
        orientation_deg = 0.0
    else:
        # Longueur des 4 côtés du rectangle englobant orienté
        side_lengths = []
        for i in range(4):
            x1, y1 = coords[i]
            x2, y2 = coords[(i + 1) % 4]
            length = math.hypot(x2 - x1, y2 - y1)
            angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            side_lengths.append((length, angle))

        # Les côtés opposés ont ~la même longueur : on garde les deux valeurs distinctes
        side_lengths.sort(key=lambda t: t[0])
        profondeur_brut, angle_p = side_lengths[0]
        largeur_brut, angle_l = side_lengths[-1]

        # Orientation du bâtiment = angle du côté le plus long par rapport au Nord.
        # En Lambert-93, l'axe Y pointe vers le Nord et l'axe X vers l'Est, donc
        # l'angle "géographique" (0° = Nord, sens horaire) se déduit de l'angle
        # trigonométrique standard (0° = Est, sens anti-horaire) par : 90 - angle.
        orientation_deg = (90 - angle_l) % 180

    largeur_m = _clamp(round(largeur_brut, 2))
    profondeur_m = _clamp(round(profondeur_brut, 2))

    surface_sol_m2 = round(working_geom.area, 1)
    surface_rectangle_m2 = round(mrr.area, 1)
    compacite = round(surface_sol_m2 / surface_rectangle_m2, 3) if surface_rectangle_m2 else 1.0

    centroid = working_geom.centroid

    return {
        "largeur_m": largeur_m,
        "profondeur_m": profondeur_m,
        "orientation_deg": round(orientation_deg, 1),
        "surface_sol_m2": surface_sol_m2,
        "surface_rectangle_m2": surface_rectangle_m2,
        "compacite": compacite,
        "centroid": {"x": round(centroid.x, 1), "y": round(centroid.y, 1)},
        "clamped": largeur_brut < MIN_DIM_M or largeur_brut > MAX_DIM_M
        or profondeur_brut < MIN_DIM_M or profondeur_brut > MAX_DIM_M,
    }


if __name__ == "__main__":
    # Auto-test avec les deux géométries fournies dans merged_input.json
    # et l'exemple mentionné dans les notes de projet.
    examples = {
        "bdnb_merged_input": {
            "type": "MultiPolygon",
            "coordinates": [[[[318045.6, 6706028.4],
                               [318055.2, 6706025.1],
                               [318058.3, 6706034.7],
                               [318048.7, 6706038.0],
                               [318046.9, 6706032.2],
                               [318041.5, 6706034.1],
                               [318038.4, 6706024.5],
                               [318045.6, 6706028.4]]]],
        },
        "geom_groupe_note_projet": {
            "type": "MultiPolygon",
            "coordinates": [[[[880673.1, 6543035.3],
                               [880669.1, 6543024.3],
                               [880678.7, 6543020.9],
                               [880682.5, 6543031.9],
                               [880673.1, 6543035.3]]]],
        },
    }
    for name, g in examples.items():
        print(f"--- {name} ---")
        print(compute_house_footprint(g))
