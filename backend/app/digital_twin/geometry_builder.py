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
la main, pour rester dans le perimetre de `requirements.txt` actuel. Ces
primitives vivent desormais dans `app.digital_twin.footprint`, qui produit
en plus l'EMPRISE POLYGONALE REELLE (bloc `footprint`) consommee par la
scene 3D. Le rectangle englobant reste calcule ici, mais il n'est plus la
seule description du bati : c'est le repli pour les biens sans geometrie
BDNB exploitable, et le socle de retro-compatibilite du contrat
(`largeur_m` / `longueur_m` / `orientation_deg`, toujours renseignes).
"""

from __future__ import annotations

import math
from typing import Any, TypedDict

from app.digital_twin.footprint import (
    classify_type_batiment,
    convex_hull as _convex_hull,
    estimate_street_facing_zone,
    extract_footprint,
    min_area_rect as _min_area_rect,
)

# ---------------------------------------------------------------------------
# 1. Geometrie plane : enveloppe convexe + rectangle englobant minimal
# ---------------------------------------------------------------------------

Point = tuple[float, float]


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

_ORIENTATIONS_VALIDES = {"nord", "sud", "est", "ouest"}


def _ouvertures_from_bdnb(batiment: dict[str, Any]) -> dict[str, Any]:
    """Fenetres/menuiseries/balcon reels, issus du DPE du batiment (quand il
    existe dans la BDNB — voir README section "Jumeau numerique 3D").

    Champs source : `l_orientation_baie_vitree` (liste des facades qui ont
    reellement des fenetres) et `pourcentage_surface_baie_vitree_exterieur`
    (ratio reel de surface vitree) proviennent du DPE ; ils ne sont PAS
    toujours renseignes (couverture DPE partielle du parc). Quand ils sont
    absents, `disponible` reste a False et aucune fenetre n'est fabriquee —
    conformement au principe du projet de ne jamais inventer une donnee de
    facade qui n'existe dans aucune source.

    `has_balcony` est verifie independamment (peut etre connu meme si les
    baies vitrees ne le sont pas, ou inversement, dans quelques reponses
    BDNB observees).
    """
    orientations_brutes = batiment.get("l_orientation_baie_vitree")
    ratio = batiment.get("pourcentage_surface_baie_vitree_exterieur")

    facades: list[str] = []
    if isinstance(orientations_brutes, list):
        facades = [
            f"murs_{mot.strip().lower()}"
            for mot in orientations_brutes
            if isinstance(mot, str) and mot.strip().lower() in _ORIENTATIONS_VALIDES
        ]

    disponible = bool(facades) and isinstance(ratio, (int, float))

    presence_balcon = batiment.get("presence_balcon")
    has_balcony = bool(presence_balcon) if isinstance(presence_balcon, bool) else None

    return {
        "disponible": disponible,
        "facades_avec_vitrage": facades if disponible else [],
        "ratio_vitrage": round(float(ratio), 3) if disponible else None,
        "has_balcony": has_balcony,
        "menuiserie_materiau": batiment.get("type_materiaux_menuiserie"),
        "fermeture_type": batiment.get("type_fermeture"),
        "vitrage_type": batiment.get("type_vitrage"),
    }


def build_geometry_from_bdnb(
    batiment: dict[str, Any],
    formulaire: dict[str, Any] | None = None,
    adresse: dict[str, Any] | None = None,
) -> GeometryResult:
    """Construit le bloc `geometry` du contrat digital_twin_agent.

    `batiment` : un enregistrement `batiment_groupe_complet` tel que renvoye
    par la BDNB (un element de `donnees["batiment"]` cote connecteur, ou
    directement `value[0]` si on consomme la reponse brute de l'API BDNB).

    `formulaire` : champs saisis explicitement par l'utilisateur (priorite 1
    sur l'inference BDNB, cf. README section "digital_twin_agent").

    `adresse` : bloc `building_data["adresse"]` de collector_agent (label,
    lat, lon...). Sert uniquement a estimer la facade orientee vers la rue
    (`entree_facade`), a partir du point d'adresse geocode — voir
    `app.digital_twin.footprint.estimate_street_facing_zone`. Aucun impact
    sur le reste de la geometrie si absent.
    """
    formulaire = formulaire or {}
    champs_manquants: list[str] = []
    champs_ok: list[str] = []

    # -- emprise au sol : polygone reel (prioritaire) + rectangle englobant --
    # Le polygone est ce qui permet a la scene 3D d'extruder la vraie forme
    # du bati (L, U, immeuble en cour, multipolygone...) au lieu d'une boite.
    # Le rectangle reste calcule dans tous les cas : le contrat expose
    # toujours largeur/longueur/orientation, et c'est le seul repli quand la
    # BDNB ne fournit pas de geometrie exploitable.
    geom_groupe = batiment.get("geom_groupe")
    footprint = extract_footprint(geom_groupe)
    rect = bounding_rect_from_geom_groupe(geom_groupe)
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

    # -- forme et type de bati, deduits du polygone reel --
    # `footprint_shape` etait jusqu'ici fige a "rectangulaire" : il reflete
    # maintenant la forme reellement classee a partir des sommets BDNB.
    forme_emprise = formulaire.get("footprint_shape") or (footprint or {}).get("forme") or "rectangulaire"
    surface_emprise = (footprint or {}).get("surface_m2") or batiment.get("surface_emprise_sol") or batiment.get("s_geom_groupe")
    type_batiment = formulaire.get("type_batiment") or classify_type_batiment(
        floors_count=floors_count,
        hauteur_m=batiment.get("hauteur_mean"),
        surface_emprise_m2=surface_emprise,
        usage_bdnb=batiment.get("usage_niveau_1_txt"),
    )
    if footprint:
        champs_ok += ["footprint", "footprint_shape", "type_batiment"]
    else:
        champs_manquants.append("footprint")
        champs_ok.append("type_batiment")

    # -- ouvertures reelles (DPE) : fenetres/balcon/menuiserie --
    ouvertures = _ouvertures_from_bdnb(batiment)
    if ouvertures["disponible"]:
        champs_ok.append("ouvertures")
    else:
        champs_manquants.append("ouvertures")
    if ouvertures["has_balcony"] is not None:
        champs_ok.append("ouvertures.has_balcony")

    # -- facade orientee rue, pour la porte d'entree --
    # Estimee a partir du point d'adresse geocode (voir docstring de
    # `estimate_street_facing_zone`) : jamais une position arbitraire, mais
    # jamais garantie non plus (rue non determinable -> None, pas de porte).
    entree_facade = None
    if adresse:
        entree_facade = estimate_street_facing_zone(geom_groupe, adresse.get("lat"), adresse.get("lon"))
    if entree_facade:
        champs_ok.append("entree_facade")
    else:
        champs_manquants.append("entree_facade")

    # -- champs non couverts par la BDNB : formulaire ou a completer --
    geometry: dict[str, Any] = {
        "footprint_shape": forme_emprise,
        "footprint": footprint,
        "type_batiment": type_batiment,
        "surface_emprise_m2": round(surface_emprise, 1) if isinstance(surface_emprise, (int, float)) else None,
        "largeur_m": largeur_m,
        "longueur_m": longueur_m,
        "orientation_deg": orientation_deg,
        "floors_count": floors_count,
        "hauteur_sous_plafond_m": hauteur_sous_plafond_m,
        "roof_shape": roof_shape,
        "pente_toit_deg": pente_toit_deg,
        "materiau_mur": materiau_mur,
        "materiau_toiture": materiau_toiture,
        "ouvertures": ouvertures,
        "entree_facade": entree_facade,
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
