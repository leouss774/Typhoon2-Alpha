"""
Modele Pydantic du bloc `geometry` du contrat de sortie du jumeau numerique
(cf. README racine, section "Jumeau numerique 3D — contrat de sortie", et
`recommendation_travaux/next steps/README_noeud_jumeau_numerique.md`).

Produit par `app.digital_twin.geometry_builder.build_geometry_from_bdnb`,
consomme tel quel par `frontend/*/scene/house-scene.js` (cote assurance) et
par le front de test `frontend/jumeau_numerique/index.html`.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RoofShape = Literal["deux_pans", "quatre_pans", "croupe", "plat", "mansarde"]
# Formes classees par `app.digital_twin.footprint.classify_forme` a partir
# des sommets reels de `geom_groupe` (BDNB), et non plus figees a
# "rectangulaire".
FootprintShape = Literal[
    "rectangulaire",
    "en_L",
    "en_T",
    "en_U",
    "en_croix",
    "multipolygone",
    "irreguliere",
]
TypeBatiment = Literal["maison_individuelle", "immeuble"]
GaragePosition = Literal["nord", "sud", "est", "ouest"]
ZoneMur = Literal["murs_nord", "murs_sud", "murs_est", "murs_ouest"]


class FootprintPolygon(BaseModel):
    """Un polygone de l'emprise, en metres dans le repere local de la scene
    (x = Est, z = Sud, origine au centre du bati). Contour ouvert : la
    fermeture est implicite."""

    exterieur: list[tuple[float, float]] = Field(min_length=3)
    trous: list[list[tuple[float, float]]] = Field(default_factory=list)


class Footprint(BaseModel):
    """Emprise au sol reelle, extraite de `geom_groupe` (BDNB).

    C'est ce bloc qui permet a la scene Three.js d'extruder la forme exacte
    du bati plutot qu'une boite deduite du seul rectangle englobant.
    """

    polygones: list[FootprintPolygon] = Field(min_length=1)
    forme: FootprintShape
    nb_polygones: int = Field(ge=1)
    nb_sommets: int = Field(ge=3)
    surface_m2: float = Field(gt=0)
    perimetre_m: float = Field(gt=0)
    # 1.0 = rectangle parfait. Plus la valeur est basse, plus l'ancienne
    # approximation en boite s'ecartait du bati reel.
    rectangularite: float = Field(ge=0, le=1)
    source_crs: str | None = None


class Ouvertures(BaseModel):
    """Fenetres/menuiserie/balcon reels, issus du DPE du batiment quand il
    existe dans la BDNB (`app.digital_twin.geometry_builder._ouvertures_from_bdnb`).

    `disponible=False` signifie que la couverture DPE est absente pour ce
    bien : aucune fenetre n'est alors a fabriquer, plutot que d'en deviner
    une position/quantite plausible.
    """

    disponible: bool = False
    facades_avec_vitrage: list[ZoneMur] = Field(default_factory=list)
    ratio_vitrage: float | None = Field(default=None, ge=0, le=1)
    has_balcony: bool | None = None
    menuiserie_materiau: str | None = None
    fermeture_type: str | None = None
    vitrage_type: str | None = None


class HouseGeometry(BaseModel):
    footprint_shape: FootprintShape = "rectangulaire"
    # None quand la BDNB ne fournit aucune geometrie exploitable pour ce
    # bien : le rendu retombe alors sur largeur/longueur/orientation.
    footprint: Footprint | None = None
    type_batiment: TypeBatiment = "maison_individuelle"
    surface_emprise_m2: float | None = Field(default=None, gt=0)

    largeur_m: float = Field(gt=0)
    longueur_m: float = Field(gt=0)
    orientation_deg: float = Field(default=0.0, ge=0, lt=180)

    floors_count: int = Field(default=1, ge=1, le=6)
    hauteur_sous_plafond_m: float = Field(default=2.6, ge=2.0, le=3.5)

    roof_shape: RoofShape = "deux_pans"
    pente_toit_deg: float = Field(default=35.0, ge=0, le=60)

    materiau_mur: str | None = None
    materiau_toiture: str | None = None

    ouvertures: Ouvertures = Field(default_factory=Ouvertures)
    # Facade estimee orientee vers la rue (voir
    # `app.digital_twin.footprint.estimate_street_facing_zone`) : sert a
    # placer la porte d'entree. None si non determinable (pas d'adresse
    # geocodee, ou geometrie non exploitable).
    entree_facade: ZoneMur | None = None

    has_basement: bool | None = None
    has_cellar: bool | None = None
    has_garage: bool | None = None
    garage_position: GaragePosition | None = None
    has_garden: bool | None = None
    garden_surface_m2: float | None = Field(default=None, ge=0)


class GeometryBuildReport(BaseModel):
    """Metadonnees de fabrication du bloc geometry — pas dans le contrat
    frontend, mais utile a l'orchestrateur pour decider s'il faut brancher
    l'etape de completion LLM (README §4) avant de renvoyer le contrat."""

    geometry: HouseGeometry
    champs_manquants: list[str] = Field(default_factory=list)
    champs_ok: list[str] = Field(default_factory=list)
