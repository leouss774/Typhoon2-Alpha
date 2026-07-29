"""
digital_twin_agent — partie deterministe (voir
`recommendation_travaux/next steps/README_noeud_jumeau_numerique.md`).

Traduit un enregistrement BDNB (`batiment_groupe_complet`, tel que renvoye par
`app.connectors.bdnb.fetch_bdnb` -> `donnees["batiment"]`) en bloc `geometry`
du contrat de sortie du jumeau numerique (cf. section "Jumeau numerique 3D —
contrat de sortie" du README racine).

Deux familles de champs, traitees differemment :

- Champs calculables de facon deterministe a partir de la geometrie/des
  attributs BDNB (emprise, hauteur, materiaux) : toujours renseignes ici,
  jamais devines par un LLM.
- Champs que la BDNB ne fournit pas et que le formulaire ne couvre pas encore
  (cave, sous-sol, garage, jardin) : on ne les invente pas dans cette
  fonction. Ils sont laisses a None et listes dans `champs_manquants`, pour
  etre completes soit par le formulaire (priorite 1, cf. README), soit par
  l'etape de completion LLM a brancher plus tard (priorite 2, section
  "Role de l'IA dans ce noeud"). C'est cette liste qui doit etre passee au
  LLM pour qu'il ne complete QUE ce qui manque reellement.

Aucune dependance geo externe (pas de shapely) : le rectangle englobant
minimal est calcule via une enveloppe convexe + rotating calipers ecrits a
la main, pour rester dans le perimetre de `requirements.txt` actuel.
"""

from __future__ import annotations

import math
from typing import Any, TypedDict

# ---------------------------------------------------------------------------
# 1. Geometrie plane : enveloppe convexe + rectangle englobant minimal
# ---------------------------------------------------------------------------

Point = tuple[float, float]


def _convex_hull(points: list[Point]) -> list[Point]:
    """Enveloppe convexe (monotone chain d'Andrew). O(n log n)."""
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
    """Rectangle englobant minimal (rotating calipers) sur une enveloppe convexe.

    Retourne (largeur, longueur, angle_deg) ou angle_deg est l'orientation
    du cote le plus long du rectangle, en degres, mesuree depuis l'axe Est
    (X), sens trigonometrique — a reprojeter en cap compas par l'appelant si
    besoin.
    """
    n = len(hull)
    if n < 3:
        # Degenere (polygone quasi ponctuel/lineaire) : pas de rectangle
        # sense, l'appelant retombera sur un defaut.
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
    """Aplati les coordonnees d'un (Multi)Polygon GeoJSON en liste de points 2D."""
    if not geom_groupe:
        return []
    coords = geom_groupe.get("coordinates")
    if not coords:
        return []
    geom_type = geom_groupe.get("type", "Polygon")

    points: list[Point] = []
    if geom_type == "MultiPolygon":
        # coords = [ [ [ [x,y], ... ] , trous... ], autres polygones... ]
        for polygon in coords:
            ring = polygon[0]
            points.extend((float(x), float(y)) for x, y in ring)
    elif geom_type == "Polygon":
        ring = coords[0]
        points.extend((float(x), float(y)) for x, y in ring)
    return points


def bounding_rect_from_geom_groupe(
    geom_groupe: dict[str, Any] | None,
) -> tuple[float, float, float] | None:
    """(largeur_m, longueur_m, orientation_deg) via rectangle englobant minimal.

    orientation_deg : cap compas (0 = nord, sens horaire) du grand cote du
    batiment, modulo 90 (une facade et son opposee sont indiscernables pour
    une simple boite rectangulaire). Retourne None si la geometrie est
    absente ou degeneree.
    """
    points = _extract_polygon_points(geom_groupe)
    if len(points) < 3:
        return None

    hull = _convex_hull(points)
    largeur, longueur, angle_from_east = _min_area_rect(hull)
    if largeur <= 0 or longueur <= 0:
        return None

    # angle_from_east (trigo, axe X=Est) -> cap compas (0=Nord, horaire)
    bearing = (90.0 - angle_from_east) % 90.0
    return (round(largeur, 2), round(longueur, 2), round(bearing, 1))


# ---------------------------------------------------------------------------
# 2. Materiaux : normalisation des libelles BDNB -> slug + pente par defaut
# ---------------------------------------------------------------------------

_MATERIAU_SLUG_OVERRIDES = {
    "meuliere": "meuliere",
    "parpaing": "parpaing_enduit",
    "pierre": "pierre_de_taille",
    "brique": "brique",
    "beton": "beton",
    "bois": "bois",
    "torchis": "torchis",
    "pan de bois": "pan_de_bois",
}

_TOITURE_PENTE_DEG = {
    "ardoises": 42.0,
    "ardoise": 42.0,
    "tuiles": 33.0,
    "tuile": 33.0,
    "tuiles plates": 45.0,
    "zinc": 15.0,
    "bac_acier": 12.0,
    "beton": 5.0,
    "vegetalise": 3.0,
}


def _slugify(label: str | None) -> str | None:
    if not label:
        return None
    normalized = label.strip().lower().replace(" ", "_").replace("-", "_")
    for key, slug in _MATERIAU_SLUG_OVERRIDES.items():
        if key in normalized:
            return slug
    return normalized


def _pente_from_materiau_toiture(materiau_toiture_slug: str | None) -> float:
    if not materiau_toiture_slug:
        return 35.0  # defaut generique (README §3 : toit 2 pans par defaut)
    for key, pente in _TOITURE_PENTE_DEG.items():
        if key in materiau_toiture_slug:
            return pente
    return 35.0


# ---------------------------------------------------------------------------
# 3. Etages / hauteur sous plafond
# ---------------------------------------------------------------------------

_HAUTEUR_ETAGE_TYPE_M = 2.7  # cf. README §3 : "hauteur d'etage type (~2,5-3 m)"


def _floors_and_level_height(
    nb_niveau: int | None, hauteur_mean: float | None
) -> tuple[int, float]:
    if nb_niveau and nb_niveau > 0:
        floors = int(nb_niveau)
    elif hauteur_mean and hauteur_mean > 0:
        floors = max(1, round(hauteur_mean / _HAUTEUR_ETAGE_TYPE_M))
    else:
        floors = 1

    if hauteur_mean and hauteur_mean > 0:
        level_height = hauteur_mean / floors
    else:
        level_height = _HAUTEUR_ETAGE_TYPE_M

    # bornes raisonnables pour eviter une geometrie degenere en aval (rendu 3D)
    level_height = min(max(level_height, 2.2), 3.4)
    floors = min(max(floors, 1), 6)
    return floors, round(level_height, 2)


# ---------------------------------------------------------------------------
# 4. Assemblage du bloc `geometry`
# ---------------------------------------------------------------------------

class GeometryResult(TypedDict):
    geometry: dict[str, Any]
    champs_manquants: list[str]
    champs_ok: list[str]


# Champs que la BDNB ne fournit pas dans ce payload et que ni le formulaire
# ni un calcul deterministe ne peuvent combler ici -> a completer par
# l'etape LLM contrainte (README §4) ou par le formulaire (priorite 1).
_CHAMPS_A_COMPLETER = ["has_basement", "has_cellar", "has_garage", "has_garden"]


def build_geometry_from_bdnb(
    batiment: dict[str, Any],
    formulaire: dict[str, Any] | None = None,
) -> GeometryResult:
    """Construit le bloc `geometry` du contrat digital_twin_agent.

    `batiment` : un enregistrement `batiment_groupe_complet` tel que renvoye
    par la BDNB (un element de `donnees["batiment"]` cote connecteur, ou
    directement `value[0]` si on consomme la reponse brute de l'API BDNB).

    `formulaire` : champs saisis explicitement par l'utilisateur (priorite 1
    sur l'inference BDNB, cf. README section "digital_twin_agent").
    """
    formulaire = formulaire or {}
    champs_manquants: list[str] = []
    champs_ok: list[str] = []

    # -- emprise au sol --
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
        # dernier recours : surface d'emprise au sol connue mais pas de
        # polygone exploitable -> boite carree equivalente
        surface = batiment.get("surface_emprise_sol") or batiment.get("s_geom_groupe")
        side = round(math.sqrt(surface), 2) if surface else 8.0
        largeur_m, longueur_m, orientation_deg = side, side, 0.0
        champs_manquants.append("orientation_deg")

    # -- etages / hauteur --
    floors_count, hauteur_sous_plafond_m = _floors_and_level_height(
        batiment.get("nb_niveau"), batiment.get("hauteur_mean")
    )
    champs_ok += ["floors_count", "hauteur_sous_plafond_m"]

    # -- materiaux --
    materiau_mur = formulaire.get("materiau_mur") or _slugify(batiment.get("mat_mur_txt"))
    materiau_toiture = formulaire.get("materiau_toiture") or _slugify(batiment.get("mat_toit_txt"))
    if materiau_mur:
        champs_ok.append("materiau_mur")
    else:
        champs_manquants.append("materiau_mur")
    if materiau_toiture:
        champs_ok.append("materiau_toiture")
    else:
        champs_manquants.append("materiau_toiture")

    # -- toiture (fallback typologique deterministe, cf. README §3) --
    roof_shape = formulaire.get("roof_shape", "deux_pans")
    pente_toit_deg = formulaire.get("pente_toit_deg") or _pente_from_materiau_toiture(materiau_toiture)
    champs_ok += ["roof_shape", "pente_toit_deg"]

    # -- champs non couverts par la BDNB : formulaire ou a completer --
    geometry: dict[str, Any] = {
        "footprint_shape": formulaire.get("footprint_shape", "rectangulaire"),
        "largeur_m": largeur_m,
        "longueur_m": longueur_m,
        "orientation_deg": orientation_deg,
        "floors_count": floors_count,
        "hauteur_sous_plafond_m": hauteur_sous_plafond_m,
        "roof_shape": roof_shape,
        "pente_toit_deg": pente_toit_deg,
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

    if "garden_surface_m2" in formulaire:
        geometry["garden_surface_m2"] = formulaire["garden_surface_m2"]
    if "garage_position" in formulaire:
        geometry["garage_position"] = formulaire["garage_position"]

    return {
        "geometry": geometry,
        "champs_manquants": champs_manquants,
        "champs_ok": champs_ok,
    }
