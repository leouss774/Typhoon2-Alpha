"""
Emprise au sol reelle du batiment, a partir du polygone BDNB `geom_groupe`.

Jusqu'ici, `geometry_builder` reduisait ce polygone a son rectangle englobant
minimal (largeur x longueur x orientation) : le rendu 3D affichait donc une
boite, quelle que soit la forme reelle du bati. Ce module conserve le
polygone lui-meme, pour que la scene Three.js extrude l'emprise exacte.

Ce qu'il produit (bloc `footprint` du contrat) :

  - `polygones` : la liste des polygones (exterieur + trous eventuels),
    exprimes en METRES dans un repere local centre sur le batiment, avec
    x = Est et z = Sud. C'est la convention de la scene Three.js, ou le nord
    pointe vers -z (cf. `murs_nord` place a z negatif dans index.html).
  - `forme` : classification de l'emprise (rectangulaire, en_L, en_T, en_U,
    en_croix, multipolygone, irreguliere).
  - `surface_m2` / `perimetre_m` : mesures reelles, trous deduits.
  - `rectangularite` : aire du polygone / aire de son rectangle englobant
    minimal. 1.0 = rectangle parfait. C'est l'indicateur qui dit a quel
    point l'ancienne approximation en boite etait fausse.

Systeme de coordonnees : la BDNB renvoie `geom_groupe` en EPSG:2154
(Lambert-93), donc deja en metres — verifie sur des reponses reelles de
`api.bdnb.io`. Le cas EPSG:4326 (degres) est gere par une projection
equirectangulaire locale, suffisamment exacte a l'echelle d'un batiment.

Aucune dependance geo externe (ni shapely, ni pyproj) : tout est ecrit a la
main pour rester dans le perimetre de `requirements.txt`, comme le reste de
`geometry_builder`.
"""

from __future__ import annotations

import math
from typing import Any

Point = tuple[float, float]
Ring = list[Point]

# Un polygone dont l'aire est sous ce seuil est du bruit de numerisation
# (abri de jardin numerise a part, artefact de decoupe cadastrale) : on ne
# le fait pas apparaitre dans la modelisation 3D.
_SURFACE_MIN_POLYGONE_M2 = 6.0

# Un polygone secondaire pesant moins que cette fraction du plus grand est
# ignore lui aussi : la BDNB regroupe parfois un batiment principal avec des
# annexes minuscules, qui parasitent la classification de forme.
_FRACTION_MIN_POLYGONE = 0.06

# Tolerance de simplification (Douglas-Peucker) : la BDNB numerise les
# facades avec des points tous les ~30 cm, ce qui donne des murs "en
# escalier" a l'ecran. 0.35 m lisse ce bruit sans deformer une vraie
# decrochee de facade.
_TOLERANCE_SIMPLIFICATION_M = 0.35

# Deux aretes formant un angle plus plat que ce seuil sont fusionnees.
_ANGLE_COLINEAIRE_DEG = 7.0


# ---------------------------------------------------------------------------
# 1. Primitives geometriques planes
# ---------------------------------------------------------------------------

def _signed_area(ring: Ring) -> float:
    """Aire signee (shoelace). Positive si le contour tourne dans le sens
    trigonometrique dans le repere (x, z) utilise ici."""
    total = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _perimeter(ring: Ring) -> float:
    total = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i + 1) % n]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def convex_hull(points: list[Point]) -> list[Point]:
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


def min_area_rect(hull: list[Point]) -> tuple[float, float, float]:
    """Rectangle englobant minimal (rotating calipers) sur une enveloppe convexe.

    Retourne (petit_cote, grand_cote, angle_deg) ou angle_deg est
    l'orientation du grand cote, en degres depuis l'axe X, sens
    trigonometrique.
    """
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


def _point_in_ring(point: Point, ring: Ring) -> bool:
    """Test d'appartenance par lancer de rayon (ray casting)."""
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


def _point_in_polygon(point: Point, exterieur: Ring, trous: list[Ring]) -> bool:
    if not _point_in_ring(point, exterieur):
        return False
    return not any(_point_in_ring(point, trou) for trou in trous)


# ---------------------------------------------------------------------------
# 2. Simplification des contours
# ---------------------------------------------------------------------------

def _douglas_peucker(ring: Ring, tolerance: float) -> Ring:
    """Simplification Douglas-Peucker sur une polyligne ouverte."""
    if len(ring) < 3:
        return list(ring)

    def distance_to_segment(p: Point, a: Point, b: Point) -> float:
        (px, py), (ax, ay), (bx, by) = p, a, b
        dx, dy = bx - ax, by - ay
        if dx == 0 and dy == 0:
            return math.hypot(px - ax, py - ay)
        t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (ax + t * dx), py - (ay + t * dy))

    def recurse(points: Ring) -> Ring:
        if len(points) < 3:
            return list(points)
        first, last = points[0], points[-1]
        index, max_dist = 0, 0.0
        for i in range(1, len(points) - 1):
            dist = distance_to_segment(points[i], first, last)
            if dist > max_dist:
                index, max_dist = i, dist
        if max_dist <= tolerance:
            return [first, last]
        return recurse(points[: index + 1])[:-1] + recurse(points[index:])

    return recurse(ring)


def _drop_collinear(ring: Ring, angle_tol_deg: float) -> Ring:
    """Fusionne les sommets quasi alignes (bruit de numerisation BDNB)."""
    if len(ring) < 4:
        return list(ring)

    kept: Ring = []
    n = len(ring)
    for i in range(n):
        prev_pt = ring[(i - 1) % n]
        cur = ring[i]
        next_pt = ring[(i + 1) % n]
        v1 = (cur[0] - prev_pt[0], cur[1] - prev_pt[1])
        v2 = (next_pt[0] - cur[0], next_pt[1] - cur[1])
        n1, n2 = math.hypot(*v1), math.hypot(*v2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        cos_angle = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        deviation_deg = math.degrees(math.acos(cos_angle))
        if deviation_deg > angle_tol_deg:
            kept.append(cur)
    return kept if len(kept) >= 3 else list(ring)


def _normalize_ring(ring: Ring, tolerance: float) -> Ring:
    """Deduplique, simplifie et retire les sommets alignes d'un contour ferme."""
    # GeoJSON ferme ses anneaux (dernier point == premier) : on travaille en
    # contour ouvert, la fermeture est implicite partout dans ce module.
    pts = list(ring)
    if len(pts) >= 2 and math.dist(pts[0], pts[-1]) < 1e-9:
        pts = pts[:-1]

    deduped: Ring = []
    for p in pts:
        if not deduped or math.dist(deduped[-1], p) > 1e-6:
            deduped.append(p)
    if len(deduped) < 3:
        return deduped

    simplified = _douglas_peucker(deduped + [deduped[0]], tolerance)
    if len(simplified) >= 2 and math.dist(simplified[0], simplified[-1]) < 1e-9:
        simplified = simplified[:-1]
    if len(simplified) < 3:
        return deduped

    return _drop_collinear(simplified, _ANGLE_COLINEAIRE_DEG)


# ---------------------------------------------------------------------------
# 3. Lecture GeoJSON + passage en repere local metrique
# ---------------------------------------------------------------------------

def _crs_name(geom: dict[str, Any]) -> str:
    crs = geom.get("crs")
    if isinstance(crs, dict):
        props = crs.get("properties")
        if isinstance(props, dict):
            return str(props.get("name") or "")
    return ""


def _is_geographic(geom: dict[str, Any]) -> bool:
    """Vrai si les coordonnees sont en degres (lon/lat) plutot qu'en metres.

    La BDNB repond en EPSG:2154 (Lambert-93, metres) — c'est le cas nominal.
    On detecte quand meme le cas geographique, sinon des degres seraient
    silencieusement interpretes comme des metres et donneraient un batiment
    de 10 cm de large.
    """
    name = _crs_name(geom).upper()
    if "4326" in name or "CRS84" in name:
        return True
    if name:
        return False
    # CRS absent : on tranche sur l'ordre de grandeur des coordonnees.
    coords = _first_coordinate(geom)
    if coords is None:
        return False
    x, y = coords
    return abs(x) <= 180.0 and abs(y) <= 90.0


def _first_coordinate(geom: dict[str, Any]) -> Point | None:
    node: Any = geom.get("coordinates")
    while isinstance(node, list) and node:
        if len(node) >= 2 and all(isinstance(v, (int, float)) for v in node[:2]):
            return (float(node[0]), float(node[1]))
        node = node[0]
    return None


def _raw_polygons(geom: dict[str, Any]) -> list[tuple[Ring, list[Ring]]]:
    """Extrait [(exterieur, trous), ...] d'un (Multi)Polygon GeoJSON."""
    coords = geom.get("coordinates")
    if not coords:
        return []
    geom_type = str(geom.get("type") or "Polygon")

    def to_ring(raw: Any) -> Ring:
        return [(float(pt[0]), float(pt[1])) for pt in raw if len(pt) >= 2]

    polygons: list[tuple[Ring, list[Ring]]] = []
    if geom_type == "MultiPolygon":
        for polygon in coords:
            if polygon:
                polygons.append((to_ring(polygon[0]), [to_ring(r) for r in polygon[1:]]))
    elif geom_type == "Polygon":
        polygons.append((to_ring(coords[0]), [to_ring(r) for r in coords[1:]]))
    return polygons


# ---------------------------------------------------------------------------
# 4. Classification de la forme de l'emprise
# ---------------------------------------------------------------------------

# Signatures d'occupation sur une grille 3x3 calee sur le rectangle
# englobant minimal. Une case est "occupee" si le polygone la recouvre
# majoritairement. Comparer une signature a ces gabarits (toutes rotations
# et symetries) classe la forme sans avoir a raisonner sur les angles.
_GABARITS: dict[str, tuple[int, ...]] = {
    "en_L": (1, 0, 0, 1, 0, 0, 1, 1, 1),
    "en_T": (1, 1, 1, 0, 1, 0, 0, 1, 0),
    "en_U": (1, 0, 1, 1, 0, 1, 1, 1, 1),
    "en_croix": (0, 1, 0, 1, 1, 1, 0, 1, 0),
}

_SEUIL_RECTANGULARITE = 0.90
_SEUIL_OCCUPATION_CASE = 0.45


def _rotate_mask(mask: tuple[int, ...]) -> tuple[int, ...]:
    grid = [mask[0:3], mask[3:6], mask[6:9]]
    return tuple(grid[2 - j][i] for i in range(3) for j in range(3))


def _mirror_mask(mask: tuple[int, ...]) -> tuple[int, ...]:
    grid = [mask[0:3], mask[3:6], mask[6:9]]
    return tuple(v for row in grid for v in reversed(row))


def _variantes(mask: tuple[int, ...]) -> set[tuple[int, ...]]:
    variantes: set[tuple[int, ...]] = set()
    for base in (mask, _mirror_mask(mask)):
        courant = base
        for _ in range(4):
            variantes.add(courant)
            courant = _rotate_mask(courant)
    return variantes


def dominant_axis_deg(ring: Ring) -> float:
    """Orientation dominante des facades, en degres depuis l'axe X, dans
    [0, 90[.

    On ne peut PAS se servir du rectangle englobant minimal pour caler la
    grille d'analyse : pour une emprise en croix, le rectangle d'aire
    minimale est celui tourne a 45 degres (289 m^2 contre 324 m^2 pour le
    rectangle aligne sur les murs), et la signature d'occupation arrivait
    donc de travers. On prend a la place la direction dominante des aretes,
    ponderee par leur longueur : les murs d'un batiment sont massivement
    paralleles ou perpendiculaires entre eux, c'est ce qui donne le bon
    repere.

    Les directions sont 90-periodiques (un mur et son perpendiculaire
    definissent le meme repere) : la moyenne circulaire se fait donc sur
    l'angle quadruple, methode classique pour ce type de periodicite.
    """
    somme_cos = 0.0
    somme_sin = 0.0
    n = len(ring)
    for i in range(n):
        x1, z1 = ring[i]
        x2, z2 = ring[(i + 1) % n]
        longueur = math.hypot(x2 - x1, z2 - z1)
        if longueur < 1e-9:
            continue
        angle = math.atan2(z2 - z1, x2 - x1)
        somme_cos += longueur * math.cos(4 * angle)
        somme_sin += longueur * math.sin(4 * angle)

    if abs(somme_cos) < 1e-12 and abs(somme_sin) < 1e-12:
        return 0.0
    return (math.degrees(math.atan2(somme_sin, somme_cos)) / 4.0) % 90.0


def _occupancy_mask(exterieur: Ring, trous: list[Ring], angle_deg: float) -> tuple[int, ...]:
    """Signature d'occupation 3x3 du polygone, dans le repere du rectangle
    englobant minimal (donc independante de l'orientation du batiment)."""
    angle_rad = math.radians(angle_deg)
    cos_a, sin_a = math.cos(-angle_rad), math.sin(-angle_rad)

    def to_rect_frame(p: Point) -> Point:
        return (p[0] * cos_a - p[1] * sin_a, p[0] * sin_a + p[1] * cos_a)

    ext_local = [to_rect_frame(p) for p in exterieur]
    trous_local = [[to_rect_frame(p) for p in trou] for trou in trous]

    xs = [p[0] for p in ext_local]
    ys = [p[1] for p in ext_local]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    cell_w = (max_x - min_x) / 3.0
    cell_h = (max_y - min_y) / 3.0
    if cell_w <= 0 or cell_h <= 0:
        return tuple([0] * 9)

    mask: list[int] = []
    echantillons = 4
    for row in range(3):
        for col in range(3):
            dedans = 0
            for i in range(echantillons):
                for j in range(echantillons):
                    px = min_x + cell_w * (col + (i + 0.5) / echantillons)
                    py = min_y + cell_h * (row + (j + 0.5) / echantillons)
                    if _point_in_polygon((px, py), ext_local, trous_local):
                        dedans += 1
            couverture = dedans / (echantillons * echantillons)
            mask.append(1 if couverture >= _SEUIL_OCCUPATION_CASE else 0)
    return tuple(mask)


def classify_forme(
    exterieur: Ring,
    trous: list[Ring],
    nb_polygones: int,
    rectangularite: float,
) -> str:
    if nb_polygones > 1:
        return "multipolygone"
    if rectangularite >= _SEUIL_RECTANGULARITE:
        return "rectangulaire"

    mask = _occupancy_mask(exterieur, trous, dominant_axis_deg(exterieur))
    for nom, gabarit in _GABARITS.items():
        if mask in _variantes(gabarit):
            return nom
    return "irreguliere"


# ---------------------------------------------------------------------------
# 5. Type de batiment (maison individuelle / immeuble)
# ---------------------------------------------------------------------------

def classify_type_batiment(
    floors_count: int,
    hauteur_m: float | None,
    surface_emprise_m2: float | None,
    usage_bdnb: str | None = None,
) -> str:
    """Distingue un immeuble d'une maison individuelle.

    L'usage BDNB, quand il est renseigne, prime sur l'heuristique
    dimensionnelle : c'est une donnee, pas une deduction.
    """
    if usage_bdnb:
        usage = usage_bdnb.strip().lower()
        if "collectif" in usage or "immeuble" in usage:
            return "immeuble"
        if "individuel" in usage or "maison" in usage:
            return "maison_individuelle"

    if floors_count >= 4:
        return "immeuble"
    if hauteur_m is not None and hauteur_m >= 12.0:
        return "immeuble"
    if floors_count >= 3 and (surface_emprise_m2 or 0) >= 250.0:
        return "immeuble"
    return "maison_individuelle"


# ---------------------------------------------------------------------------
# 6. Lambert-93 -> WGS84 (rattacher le point d'adresse au repere du polygone)
# ---------------------------------------------------------------------------
#
# La BDNB renvoie `geom_groupe` en EPSG:2154 (Lambert-93), mais l'adresse
# geocodee par la Geoplateforme IGN (`app.connectors.geocoding`) est en
# WGS84 (lat/lon). Pour determiner de quel cote du batiment se trouve la
# rue (donc ou placer la porte d'entree), il faut comparer le centroide du
# polygone au point d'adresse DANS LE MEME REPERE : ceci est la conversion
# Lambert-93 -> WGS84 standard (projection conique conforme de Lambert a
# deux paralleles, ellipsoide GRS80), avec les constantes publiees par
# l'IGN pour Lambert-93 (paralleles 44 deg/49 deg, origine 46.5 deg/3 deg
# Est, fausse origine 700000/6600000).
#
# Ne sert qu'a rattacher UN point GPS au repere Lambert-93 du polygone : la
# reprojection du polygone lui-meme reste geree par `extract_footprint`
# (equirectangulaire locale, suffisante a l'echelle d'un batiment).

_L93_A = 6378137.0                     # demi-grand axe, ellipsoide GRS80
_L93_E = 0.0818191910428158            # premiere excentricite, GRS80
_L93_LAMBDA0 = math.radians(3.0)       # meridien central : 3 deg Est
_L93_PHI0 = math.radians(46.5)         # latitude d'origine
_L93_PHI1 = math.radians(44.0)         # premier parallele standard
_L93_PHI2 = math.radians(49.0)         # second parallele standard
_L93_X0 = 700000.0                     # fausse abscisse
_L93_Y0 = 6600000.0                    # fausse ordonnee


def _l93_m(phi: float) -> float:
    return math.cos(phi) / math.sqrt(1 - _L93_E ** 2 * math.sin(phi) ** 2)


def _l93_t(phi: float) -> float:
    return math.tan(math.pi / 4 - phi / 2) / (
        ((1 - _L93_E * math.sin(phi)) / (1 + _L93_E * math.sin(phi))) ** (_L93_E / 2)
    )


_L93_N = (math.log(_l93_m(_L93_PHI1)) - math.log(_l93_m(_L93_PHI2))) / (
    math.log(_l93_t(_L93_PHI1)) - math.log(_l93_t(_L93_PHI2))
)
_L93_F = _l93_m(_L93_PHI1) / (_L93_N * _l93_t(_L93_PHI1) ** _L93_N)
_L93_RHO0 = _L93_A * _L93_F * _l93_t(_L93_PHI0) ** _L93_N


def lambert93_to_wgs84(x: float, y: float) -> tuple[float, float]:
    """Convertit un point Lambert-93 (EPSG:2154) en (latitude, longitude) WGS84.

    Formule standard, avec correction iterative de l'excentricite
    (6 iterations : largement suffisant, la convergence est sous le
    millimetre des la 3e). Verifie par aller-retour (`wgs84_to_lambert93`
    puis reciproque) dans les tests, et par comparaison avec des adresses
    geocodees reelles dans `test_footprint.py`.
    """
    dx = x - _L93_X0
    dy = _L93_RHO0 - (y - _L93_Y0)
    rho = math.hypot(dx, dy)
    if _L93_N < 0:
        rho = -rho
    theta = math.atan2(dx, dy)
    lon = _L93_LAMBDA0 + theta / _L93_N
    t = (rho / (_L93_A * _L93_F)) ** (1.0 / _L93_N)
    phi = math.pi / 2 - 2 * math.atan(t)
    for _ in range(6):
        phi = math.pi / 2 - 2 * math.atan(
            t * ((1 - _L93_E * math.sin(phi)) / (1 + _L93_E * math.sin(phi))) ** (_L93_E / 2)
        )
    return math.degrees(phi), math.degrees(lon)


def wgs84_to_lambert93(lat: float, lon: float) -> tuple[float, float]:
    """Sens direct — sert uniquement au test d'aller-retour de `lambert93_to_wgs84`."""
    phi, lam = math.radians(lat), math.radians(lon)
    t = _l93_t(phi)
    rho = _L93_A * _L93_F * t ** _L93_N
    theta = _L93_N * (lam - _L93_LAMBDA0)
    x = _L93_X0 + rho * math.sin(theta)
    y = _L93_Y0 + _L93_RHO0 - rho * math.cos(theta)
    return x, y


def _centroid_lambert93(geom_groupe: dict[str, Any] | None) -> Point | None:
    """Centroide brut (Lambert-93) des sommets exterieurs, avant toute
    reprojection locale. Distinct du centrage fait dans `extract_footprint`
    (qui, lui, travaille deja dans le repere metrique de la scene)."""
    if not isinstance(geom_groupe, dict):
        return None
    if _is_geographic(geom_groupe):
        return None  # cas rare (WGS84) : cette estimation ne gere que Lambert-93
    polygons = _raw_polygons(geom_groupe)
    points: list[Point] = []
    for exterieur, _ in polygons:
        # GeoJSON ferme ses anneaux (dernier point == premier) : l'inclure
        # deux fois biaiserait la moyenne vers ce sommet.
        anneau = exterieur[:-1] if len(exterieur) >= 2 and math.dist(exterieur[0], exterieur[-1]) < 1e-6 else exterieur
        points.extend(anneau)
    if len(points) < 3:
        return None
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return (cx, cy)


def estimate_street_facing_zone(
    geom_groupe: dict[str, Any] | None,
    adresse_lat: float | None,
    adresse_lon: float | None,
) -> str | None:
    """Estime la facade cardinale (`murs_nord/sud/est/ouest`) la plus
    probablement orientee vers la rue, a partir du point d'adresse
    geocode.

    Principe : le point d'adresse (BAN/Geoplateforme IGN) est en pratique
    plante sur ou pres de la voie de desserte du batiment — c'est sa raison
    d'etre pour un geocodeur d'adresse. Le vecteur du centroide du batiment
    vers ce point pointe donc vers la rue. On ne fabrique aucune position :
    seule la direction cardinale la plus proche de ce vecteur reel est
    retenue.

    Retourne None si l'estimation n'est pas possible (pas de polygone
    Lambert-93 exploitable, pas d'adresse geocodee, ou point d'adresse
    confondu avec le centroide a moins d'1 metre — aucun signal directionnel
    fiable dans ce cas).
    """
    centroid = _centroid_lambert93(geom_groupe)
    if centroid is None or adresse_lat is None or adresse_lon is None:
        return None

    lat_centroid, lon_centroid = lambert93_to_wgs84(*centroid)

    # Delta local en metres (equirectangulaire, valide a l'echelle d'un
    # batiment) entre le centroide (converti en WGS84) et le point d'adresse.
    metres_par_deg_lat = 110540.0
    metres_par_deg_lon = 111320.0 * math.cos(math.radians(lat_centroid))
    d_est = (adresse_lon - lon_centroid) * metres_par_deg_lon
    d_nord = (adresse_lat - lat_centroid) * metres_par_deg_lat

    if math.hypot(d_est, d_nord) < 1.0:
        return None

    if abs(d_est) >= abs(d_nord):
        return "murs_est" if d_est > 0 else "murs_ouest"
    return "murs_nord" if d_nord > 0 else "murs_sud"


# ---------------------------------------------------------------------------
# 6bis. Point d'entree
# ---------------------------------------------------------------------------

def extract_footprint(geom_groupe: dict[str, Any] | None) -> dict[str, Any] | None:
    """Emprise reelle exploitable par la scene 3D, ou None si `geom_groupe`
    est absent ou degenere (l'appelant retombe alors sur le rectangle).
    """
    if not isinstance(geom_groupe, dict):
        return None

    polygons_source = _raw_polygons(geom_groupe)
    if not polygons_source:
        return None

    geographic = _is_geographic(geom_groupe)

    # Centre de reference : centroide des sommets exterieurs. Le repere local
    # est centre dessus pour que la scene 3D reste autour de l'origine.
    # Sommet de fermeture (dernier == premier, convention GeoJSON) exclu :
    # sinon il compte double dans la moyenne et decale le centre (sensible
    # sur un polygone a peu de sommets, ex. un simple rectangle).
    tous_points: list[Point] = []
    for exterieur, _ in polygons_source:
        anneau = exterieur[:-1] if len(exterieur) >= 2 and math.dist(exterieur[0], exterieur[-1]) < 1e-6 else exterieur
        tous_points.extend(anneau)
    if len(tous_points) < 3:
        return None
    cx = sum(p[0] for p in tous_points) / len(tous_points)
    cy = sum(p[1] for p in tous_points) / len(tous_points)

    if geographic:
        # Projection equirectangulaire locale : a l'echelle d'un batiment
        # (quelques dizaines de metres), l'erreur est negligeable.
        metres_par_degre_lat = 110540.0
        metres_par_degre_lon = 111320.0 * math.cos(math.radians(cy))

        def to_local(p: Point) -> Point:
            return ((p[0] - cx) * metres_par_degre_lon, (p[1] - cy) * metres_par_degre_lat)
    else:
        def to_local(p: Point) -> Point:
            return (p[0] - cx, p[1] - cy)

    # x = Est, z = Sud : la scene Three.js place le nord vers -z, donc l'axe
    # nord (Y du Lambert-93) est inverse ici, une bonne fois pour toutes.
    def to_scene(p: Point) -> Point:
        x, y = to_local(p)
        return (x, -y)

    polygones: list[dict[str, Any]] = []
    for exterieur_src, trous_src in polygons_source:
        exterieur = _normalize_ring([to_scene(p) for p in exterieur_src], _TOLERANCE_SIMPLIFICATION_M)
        if len(exterieur) < 3:
            continue
        aire = abs(_signed_area(exterieur))
        if aire < _SURFACE_MIN_POLYGONE_M2:
            continue

        trous: list[Ring] = []
        for trou_src in trous_src:
            trou = _normalize_ring([to_scene(p) for p in trou_src], _TOLERANCE_SIMPLIFICATION_M)
            if len(trou) >= 3 and abs(_signed_area(trou)) >= _SURFACE_MIN_POLYGONE_M2:
                trous.append(trou)

        polygones.append({"exterieur": exterieur, "trous": trous, "_aire": aire})

    if not polygones:
        return None

    # Annexes negligeables : ecartees pour ne pas fausser la classification.
    aire_max = max(p["_aire"] for p in polygones)
    polygones = [p for p in polygones if p["_aire"] >= aire_max * _FRACTION_MIN_POLYGONE]
    polygones.sort(key=lambda p: p["_aire"], reverse=True)

    # Sens de parcours normalise : exterieur en sens trigonometrique, trous
    # en sens horaire. Three.js (THREE.Shape / THREE.Path) et les normales
    # de murs cote frontend s'appuient sur cette convention.
    for polygone in polygones:
        if _signed_area(polygone["exterieur"]) < 0:
            polygone["exterieur"].reverse()
        for trou in polygone["trous"]:
            if _signed_area(trou) > 0:
                trou.reverse()

    surface_m2 = 0.0
    perimetre_m = 0.0
    for polygone in polygones:
        surface_m2 += abs(_signed_area(polygone["exterieur"]))
        surface_m2 -= sum(abs(_signed_area(t)) for t in polygone["trous"])
        perimetre_m += _perimeter(polygone["exterieur"])

    principal = polygones[0]
    hull = convex_hull(principal["exterieur"])
    largeur, longueur, angle_deg = min_area_rect(hull)
    aire_rect = largeur * longueur
    rectangularite = (abs(_signed_area(principal["exterieur"])) / aire_rect) if aire_rect > 0 else 0.0

    forme = classify_forme(
        principal["exterieur"],
        principal["trous"],
        len(polygones),
        rectangularite,
    )

    for polygone in polygones:
        polygone.pop("_aire", None)

    return {
        "polygones": [
            {
                "exterieur": [[round(x, 2), round(z, 2)] for x, z in p["exterieur"]],
                "trous": [[[round(x, 2), round(z, 2)] for x, z in t] for t in p["trous"]],
            }
            for p in polygones
        ],
        "forme": forme,
        "nb_polygones": len(polygones),
        "nb_sommets": sum(len(p["exterieur"]) for p in polygones),
        "surface_m2": round(surface_m2, 1),
        "perimetre_m": round(perimetre_m, 1),
        "rectangularite": round(rectangularite, 3),
        "source_crs": _crs_name(geom_groupe) or ("EPSG:4326 (deduit)" if geographic else "inconnu"),
    }
