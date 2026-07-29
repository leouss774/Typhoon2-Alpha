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
FootprintShape = Literal["rectangulaire", "irreguliere"]
GaragePosition = Literal["nord", "sud", "est", "ouest"]


class HouseGeometry(BaseModel):
    footprint_shape: FootprintShape = "rectangulaire"
    largeur_m: float = Field(gt=0)
    longueur_m: float = Field(gt=0)
    orientation_deg: float = Field(default=0.0, ge=0, lt=180)

    floors_count: int = Field(default=1, ge=1, le=6)
    hauteur_sous_plafond_m: float = Field(default=2.6, ge=2.0, le=3.5)

    roof_shape: RoofShape = "deux_pans"
    pente_toit_deg: float = Field(default=35.0, ge=0, le=60)

    materiau_mur: str | None = None
    materiau_toiture: str | None = None

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
