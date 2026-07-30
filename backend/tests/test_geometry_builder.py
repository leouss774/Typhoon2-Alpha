"""
Test hors-ligne de `app.digital_twin.geometry_builder`, sans acces reseau.

Fixture = un vrai enregistrement BDNB (`batiment_groupe_complet`) pour
26 Rue Victor Hugo, 37140 Bourgueil — la meme adresse que celle utilisee
dans `backend/out/37031.json` (test CLI reel de collector_agent, ou l'appel
BDNB avait echoue ce jour-la : `"bdnb": null`). Ce fixture permet de tester
la construction de la geometrie independamment de la disponibilite de l'API
BDNB au moment ou le test tourne.

A executer :
    PYTHONPATH=. python3 tests/test_geometry_builder.py
"""

from __future__ import annotations

import json

from app.digital_twin.geometry_builder import (
    bounding_rect_from_geom_groupe,
    build_geometry_from_bdnb,
)

BATIMENT_BOURGUEIL = {
    "alea_argile": "Moyen",
    "annee_construction": 1850,
    "cle_interop_adr": "37031_1591_00026",
    "code_commune_insee": "37031",
    "geom_groupe": {
        "type": "MultiPolygon",
        "crs": {"type": "name", "properties": {"name": "EPSG:2154"}},
        "coordinates": [
            [
                [
                    [486107, 6690878.5],
                    [486104.1, 6690879.6],
                    [486101.4, 6690880.5],
                    [486100.7, 6690880.8],
                    [486098.1, 6690881.8],
                    [486096.8, 6690878],
                    [486095.1, 6690872.7],
                    [486098.2, 6690871.5],
                    [486095.6, 6690862.7],
                    [486101.5, 6690859.8],
                    [486102.7, 6690863.6],
                    [486107, 6690878.5],
                ]
            ]
        ],
    },
    "hauteur_mean": 5,
    "libelle_adr_principale_ban": "26 Rue Victor Hugo 37140 Bourgueil",
    "mat_mur_txt": "MEULIERE",
    "mat_toit_txt": "ARDOISES",
    "nb_niveau": 2,
    "s_geom_groupe": 155,
    "surface_emprise_sol": 155,
}


def test_bounding_rect_matches_known_footprint():
    """Le rectangle englobant minimal doit retrouver une emprise coherente
    avec `surface_emprise_sol` (155 m^2) — le rectangle englobant est
    necessairement >= a l'aire du polygone (batiment non parfaitement
    rectangulaire, 3 adresses de rue accolees)."""
    rect = bounding_rect_from_geom_groupe(BATIMENT_BOURGUEIL["geom_groupe"])
    assert rect is not None
    largeur, longueur, orientation_deg = rect
    assert 8.0 < largeur < 12.0
    assert 18.0 < longueur < 22.0
    assert largeur * longueur >= BATIMENT_BOURGUEIL["surface_emprise_sol"]
    assert 0.0 <= orientation_deg < 90.0
    print("test_bounding_rect_matches_known_footprint OK ->", rect)


def test_build_geometry_from_bdnb_deterministic_fields():
    result = build_geometry_from_bdnb(BATIMENT_BOURGUEIL)
    geometry = result["geometry"]

    assert geometry["floors_count"] == 2  # nb_niveau fourni directement
    assert geometry["hauteur_sous_plafond_m"] == 2.5  # hauteur_mean / nb_niveau
    assert geometry["materiau_mur"] == "meuliere"
    assert geometry["materiau_toiture"] == "ardoises"
    assert geometry["roof_shape"] == "deux_pans"  # fallback typologique
    assert geometry["pente_toit_deg"] == 42.0  # heuristique ardoise
    print("test_build_geometry_from_bdnb_deterministic_fields OK ->", json.dumps(geometry, ensure_ascii=False))


def test_build_geometry_flags_missing_fields_instead_of_guessing():
    """Cave/sous-sol/garage/jardin ne sont pas dans ce payload BDNB : la
    fonction ne doit pas les deviner silencieusement, elle doit les
    remonter dans `champs_manquants` (a completer par le formulaire ou par
    l'etape LLM decrite dans la spec, pas par une heuristique cachee ici)."""
    result = build_geometry_from_bdnb(BATIMENT_BOURGUEIL)
    # BATIMENT_BOURGUEIL n'a ni champs DPE (ouvertures) ni adresse fournie
    # (entree_facade) : ces deux absences doivent aussi remonter, au meme
    # titre que cave/sous-sol/garage/jardin.
    assert set(result["champs_manquants"]) == {
        "has_basement", "has_cellar", "has_garage", "has_garden",
        "ouvertures", "entree_facade",
    }
    for champ in ("has_basement", "has_cellar", "has_garage", "has_garden"):
        assert result["geometry"][champ] is None
    print("test_build_geometry_flags_missing_fields_instead_of_guessing OK ->", result["champs_manquants"])


def test_formulaire_prend_priorite_sur_bdnb():
    """Cf. README : "champs explicites du formulaire" = priorite 1 sur
    l'inference BDNB."""
    formulaire = {"has_basement": True, "has_garage": True, "garage_position": "nord"}
    result = build_geometry_from_bdnb(BATIMENT_BOURGUEIL, formulaire=formulaire)
    assert result["geometry"]["has_basement"] is True
    assert result["geometry"]["has_garage"] is True
    assert result["geometry"]["garage_position"] == "nord"
    assert "has_basement" not in result["champs_manquants"]
    print("test_formulaire_prend_priorite_sur_bdnb OK")


def _run_all():
    test_bounding_rect_matches_known_footprint()
    test_build_geometry_from_bdnb_deterministic_fields()
    test_build_geometry_flags_missing_fields_instead_of_guessing()
    test_formulaire_prend_priorite_sur_bdnb()
    print("\nTOUS LES TESTS geometry_builder PASSENT")


if __name__ == "__main__":
    _run_all()
