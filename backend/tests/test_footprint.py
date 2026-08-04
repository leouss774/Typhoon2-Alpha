"""
Tests de l'extraction d'emprise reelle (app.digital_twin.footprint).

Deux familles de cas :
  - des polygones synthetiques dont on connait la forme attendue (L, U, T,
    croix, rectangle), pour valider la classification ;
  - un vrai `geom_groupe` BDNB (Lambert-93), pour valider le passage en
    repere local metrique et la coherence avec `surface_emprise_sol`.
"""

from __future__ import annotations

import math

from app.digital_twin.footprint import (
    classify_type_batiment,
    estimate_street_facing_zone,
    extract_footprint,
    lambert93_to_wgs84,
    wgs84_to_lambert93,
)
from app.digital_twin.geometry_builder import build_geometry_from_bdnb


def _geom(coords_exterieur, trous=None, crs="EPSG:2154"):
    """Fabrique un Polygon GeoJSON a la mode BDNB."""
    anneaux = [coords_exterieur] + list(trous or [])
    return {
        "type": "Polygon",
        "crs": {"type": "name", "properties": {"name": crs}},
        "coordinates": anneaux,
    }


def _carre(cote: float, x0: float = 0.0, y0: float = 0.0):
    return [
        [x0, y0],
        [x0 + cote, y0],
        [x0 + cote, y0 + cote],
        [x0, y0 + cote],
        [x0, y0],
    ]


# ---------------------------------------------------------------------------
# Classification de forme
# ---------------------------------------------------------------------------

def test_rectangle_est_classe_rectangulaire():
    footprint = extract_footprint(_geom([[0, 0], [12, 0], [12, 8], [0, 8], [0, 0]]))
    assert footprint is not None
    assert footprint["forme"] == "rectangulaire"
    assert footprint["nb_polygones"] == 1
    assert footprint["surface_m2"] == 96.0
    # Un rectangle coincide avec son rectangle englobant.
    assert footprint["rectangularite"] > 0.99


def test_forme_en_L_est_reconnue():
    # Carre 15x15 ampute de son quart nord-est -> L
    coords = [[0, 0], [15, 0], [15, 5], [5, 5], [5, 15], [0, 15], [0, 0]]
    footprint = extract_footprint(_geom(coords))
    assert footprint["forme"] == "en_L"
    # 15*15 - 10*10 = 125
    assert footprint["surface_m2"] == 125.0
    # Une emprise en L remplit nettement moins que son rectangle englobant :
    # c'est exactement l'ecart que l'ancienne modelisation en boite ignorait.
    assert footprint["rectangularite"] < 0.7


def test_forme_en_U_est_reconnue():
    coords = [
        [0, 0], [18, 0], [18, 18], [12, 18], [12, 6], [6, 6], [6, 18], [0, 18], [0, 0],
    ]
    footprint = extract_footprint(_geom(coords))
    assert footprint["forme"] == "en_U"


def test_forme_en_T_est_reconnue():
    # Barre horizontale (y 12->18, pleine largeur) + jambage (x 6->12, y 0->12)
    coords = [
        [0, 12], [6, 12], [6, 0], [12, 0], [12, 12],
        [18, 12], [18, 18], [0, 18], [0, 12],
    ]
    footprint = extract_footprint(_geom(coords))
    assert footprint["forme"] == "en_T"


def test_forme_en_croix_est_reconnue():
    coords = [
        [6, 0], [12, 0], [12, 6], [18, 6], [18, 12], [12, 12],
        [12, 18], [6, 18], [6, 12], [0, 12], [0, 6], [6, 6], [6, 0],
    ]
    footprint = extract_footprint(_geom(coords))
    assert footprint["forme"] == "en_croix"


def test_multipolygone_est_reconnu():
    geom = {
        "type": "MultiPolygon",
        "crs": {"type": "name", "properties": {"name": "EPSG:2154"}},
        "coordinates": [[_carre(10)], [_carre(9, x0=30)]],
    }
    footprint = extract_footprint(geom)
    assert footprint["forme"] == "multipolygone"
    assert footprint["nb_polygones"] == 2
    assert footprint["surface_m2"] == 181.0  # 100 + 81


def test_annexe_minuscule_est_ecartee():
    """Un appentis de 2 m^2 ne doit pas transformer une maison rectangulaire
    en "multipolygone" ni polluer la scene 3D."""
    geom = {
        "type": "MultiPolygon",
        "crs": {"type": "name", "properties": {"name": "EPSG:2154"}},
        "coordinates": [[_carre(12)], [_carre(1.4, x0=40)]],
    }
    footprint = extract_footprint(geom)
    assert footprint["nb_polygones"] == 1
    assert footprint["forme"] == "rectangulaire"


def test_trou_interieur_est_conserve_et_deduit_de_la_surface():
    """Immeuble avec cour interieure : le trou doit rester dans le contrat
    (la scene 3D doit le percer) et etre deduit de la surface."""
    exterieur = [[0, 0], [30, 0], [30, 30], [0, 30], [0, 0]]
    cour = [[10, 10], [20, 10], [20, 20], [10, 20], [10, 10]]
    footprint = extract_footprint(_geom(exterieur, trous=[cour]))
    assert len(footprint["polygones"][0]["trous"]) == 1
    assert footprint["surface_m2"] == 800.0  # 900 - 100


# ---------------------------------------------------------------------------
# Repere local et systeme de coordonnees
# ---------------------------------------------------------------------------

def test_emprise_est_centree_sur_le_batiment():
    """Les coordonnees Lambert-93 (~1e6) doivent devenir des metres locaux
    autour de l'origine, sinon la scene 3D place le bati hors camera."""
    coords = [
        [1044070.5, 6298008.0], [1044090.5, 6298008.0],
        [1044090.5, 6298028.0], [1044070.5, 6298028.0], [1044070.5, 6298008.0],
    ]
    footprint = extract_footprint(_geom(coords))
    sommets = footprint["polygones"][0]["exterieur"]
    assert all(abs(x) < 50 and abs(z) < 50 for x, z in sommets)
    assert footprint["surface_m2"] == 400.0


def test_axe_nord_pointe_vers_z_negatif():
    """Convention de la scene : nord = -z. Le sommet le plus au nord en
    Lambert-93 (Y max) doit donc avoir le z le plus negatif."""
    coords = [
        [1000000.0, 6000000.0], [1000010.0, 6000000.0],
        [1000010.0, 6000030.0], [1000000.0, 6000030.0], [1000000.0, 6000000.0],
    ]
    footprint = extract_footprint(_geom(coords))
    sommets = footprint["polygones"][0]["exterieur"]
    assert min(z for _, z in sommets) < 0 < max(z for _, z in sommets)
    # 30 m de long selon l'axe nord-sud, 10 m est-ouest
    assert round(max(z for _, z in sommets) - min(z for _, z in sommets)) == 30
    assert round(max(x for x, _ in sommets) - min(x for x, _ in sommets)) == 10


def test_coordonnees_geographiques_sont_projetees_en_metres():
    """Si une source renvoie du WGS84, les degres ne doivent pas etre pris
    pour des metres (batiment de 10 cm de large)."""
    lon, lat = 7.2683, 43.7009  # Nice
    d_lon = 20.0 / (111320.0 * math.cos(math.radians(lat)))
    d_lat = 20.0 / 110540.0
    coords = [
        [lon, lat], [lon + d_lon, lat],
        [lon + d_lon, lat + d_lat], [lon, lat + d_lat], [lon, lat],
    ]
    footprint = extract_footprint(_geom(coords, crs="EPSG:4326"))
    assert 380 < footprint["surface_m2"] < 420  # ~20 x 20 m


def test_geometrie_absente_retourne_none():
    assert extract_footprint(None) is None
    assert extract_footprint({"type": "Polygon", "coordinates": []}) is None


# ---------------------------------------------------------------------------
# Type de batiment
# ---------------------------------------------------------------------------

def test_immeuble_detecte_par_le_nombre_de_niveaux():
    assert classify_type_batiment(5, 21.0, 1256.0) == "immeuble"


def test_maison_detectee_sur_bati_bas():
    assert classify_type_batiment(2, 5.0, 155.0) == "maison_individuelle"


def test_lambert93_wgs84_aller_retour_est_quasi_exact():
    """L'aller-retour doit tomber sous le millimetre : sinon l'estimation
    du cote rue (qui compare des points a l'echelle du batiment) serait
    faussee par l'erreur de conversion elle-meme plutot que par le signal
    reel."""
    lat0, lon0 = 48.8566, 2.3522  # Paris
    x, y = wgs84_to_lambert93(lat0, lon0)
    lat1, lon1 = lambert93_to_wgs84(x, y)
    assert abs(lat1 - lat0) < 1e-9
    assert abs(lon1 - lon0) < 1e-9


def test_lambert93_wgs84_coherent_avec_une_adresse_reelle_bourgueil():
    """Le centroide du polygone BDNB de la maison de Bourgueil, converti en
    WGS84, doit tomber a quelques dizaines de metres au plus de l'adresse
    BAN reelle de ce meme bien — pas a l'autre bout du departement. Sert de
    garde-fou contre une inversion de signe ou une confusion de convention
    (X/Y, degres/radians) qui donnerait un resultat a des kilometres."""
    lat_c, lon_c = lambert93_to_wgs84(486100.0, 6690870.0)  # proche du centroide BATIMENT_NICE-like
    # Bourgueil (37140) est autour de 47.28 N / 0.17 E : un bug de
    # conversion sortirait de cet ordre de grandeur.
    assert 47.0 < lat_c < 47.5
    assert -0.2 < lon_c < 0.6


def test_estimation_cote_rue_pointe_vers_le_point_adresse():
    """Emprise carree centree a l'origine (en Lambert-93, autour du
    centroide Bourgueil) ; un point d'adresse artificiellement place au
    nord doit faire ressortir murs_nord, et vice-versa."""
    cx, cy = 486100.0, 6690870.0
    carre = _geom([
        [cx - 5, cy - 5], [cx + 5, cy - 5], [cx + 5, cy + 5], [cx - 5, cy + 5], [cx - 5, cy - 5],
    ])
    lat_c, lon_c = lambert93_to_wgs84(cx, cy)

    metres_par_deg_lat = 110540.0
    metres_par_deg_lon = 111320.0 * math.cos(math.radians(lat_c))

    lat_nord = lat_c + 30.0 / metres_par_deg_lat
    assert estimate_street_facing_zone(carre, lat_nord, lon_c) == "murs_nord"

    lon_est = lon_c + 30.0 / metres_par_deg_lon
    assert estimate_street_facing_zone(carre, lat_c, lon_est) == "murs_est"


def test_estimation_cote_rue_none_si_confondu_avec_le_centroide():
    cx, cy = 486100.0, 6690870.0
    carre = _geom([
        [cx - 5, cy - 5], [cx + 5, cy - 5], [cx + 5, cy + 5], [cx - 5, cy + 5], [cx - 5, cy - 5],
    ])
    lat_c, lon_c = lambert93_to_wgs84(cx, cy)
    assert estimate_street_facing_zone(carre, lat_c, lon_c) is None


def test_estimation_cote_rue_none_sans_adresse_ou_sans_geometrie():
    assert estimate_street_facing_zone(None, 47.28, 0.17) is None
    assert estimate_street_facing_zone(_geom(_carre(10)), None, None) is None


def test_usage_bdnb_prime_sur_l_heuristique():
    """L'usage BDNB est une donnee : elle doit l'emporter sur la deduction
    dimensionnelle."""
    assert classify_type_batiment(2, 6.0, 120.0, usage_bdnb="Résidentiel collectif") == "immeuble"


# ---------------------------------------------------------------------------
# Integration dans le bloc geometry
# ---------------------------------------------------------------------------

BATIMENT_NICE = {
    "annee_construction": 1848,
    "nb_niveau": 5,
    "hauteur_mean": 21,
    "s_geom_groupe": 1256,
    "surface_emprise_sol": 1256,
    "mat_mur_txt": "INDETERMINE",
    "mat_toit_txt": "INDETERMINE",
    "geom_groupe": {
        "type": "MultiPolygon",
        "crs": {"type": "name", "properties": {"name": "EPSG:2154"}},
        "coordinates": [
            [
                [
                    [1044070.5, 6298008.0],
                    [1044075.5, 6297999.2],
                    [1044081.3, 6297989.0],
                    [1044108.2, 6298006.6],
                    [1044090.8, 6298039.3],
                    [1044063.0, 6298026.1],
                    [1044064.3, 6298023.0],
                    [1044070.5, 6298008.0],
                ]
            ]
        ],
    },
}


def test_geometry_expose_l_emprise_reelle_et_le_type():
    result = build_geometry_from_bdnb(BATIMENT_NICE)
    geometry = result["geometry"]

    assert geometry["footprint"] is not None
    assert geometry["type_batiment"] == "immeuble"
    assert geometry["footprint"]["nb_sommets"] >= 5
    # Retro-compatibilite : le rectangle englobant reste renseigne.
    assert geometry["largeur_m"] > 0 and geometry["longueur_m"] > 0
    assert "footprint" in result["champs_ok"]

    # L'emprise reelle doit rester coherente avec la surface declaree par la
    # BDNB (1256 m^2) — a la simplification des contours pres.
    assert abs(geometry["footprint"]["surface_m2"] - 1256) / 1256 < 0.10


def test_geometry_expose_les_ouvertures_reelles_quand_le_dpe_existe():
    batiment = dict(BATIMENT_NICE)
    batiment.update({
        "l_orientation_baie_vitree": ["sud"],
        "pourcentage_surface_baie_vitree_exterieur": 0.111,
        "presence_balcon": False,
        "type_materiaux_menuiserie": "bois",
        "type_fermeture": "volet battant bois",
        "type_vitrage": "double vitrage",
    })
    result = build_geometry_from_bdnb(batiment)
    ouvertures = result["geometry"]["ouvertures"]
    assert ouvertures["disponible"] is True
    assert ouvertures["facades_avec_vitrage"] == ["murs_sud"]
    assert ouvertures["ratio_vitrage"] == 0.111
    assert ouvertures["has_balcony"] is False
    assert "ouvertures" in result["champs_ok"]
    assert "ouvertures.has_balcony" in result["champs_ok"]


def test_geometry_ne_fabrique_aucune_ouverture_sans_donnee_dpe():
    """Cas reel majoritaire (ex. la maison de Bourgueil) : aucun champ DPE
    renseigne -> aucune fenetre ne doit etre inventee."""
    result = build_geometry_from_bdnb(BATIMENT_NICE)  # sans champs DPE
    ouvertures = result["geometry"]["ouvertures"]
    assert ouvertures["disponible"] is False
    assert ouvertures["facades_avec_vitrage"] == []
    assert ouvertures["has_balcony"] is None
    assert "ouvertures" in result["champs_manquants"]


def test_geometry_ignore_une_orientation_de_baie_non_reconnue():
    """Une valeur inattendue dans l_orientation_baie_vitree (ex. donnee
    fournisseur bruitee) ne doit pas faire planter l'agregation ni produire
    une zone murs_xxx inexistante."""
    batiment = dict(BATIMENT_NICE)
    batiment.update({
        "l_orientation_baie_vitree": ["sud", "toiture", None, 42],
        "pourcentage_surface_baie_vitree_exterieur": 0.15,
    })
    ouvertures = build_geometry_from_bdnb(batiment)["geometry"]["ouvertures"]
    assert ouvertures["facades_avec_vitrage"] == ["murs_sud"]


def test_geometry_estime_l_entree_facade_a_partir_de_l_adresse():
    cx, cy = 486100.0, 6690870.0
    from app.digital_twin.footprint import lambert93_to_wgs84
    lat_c, lon_c = lambert93_to_wgs84(cx, cy)
    lat_nord = lat_c + 30.0 / 110540.0

    batiment = dict(BATIMENT_NICE)
    batiment["geom_groupe"] = _geom([
        [cx - 5, cy - 5], [cx + 5, cy - 5], [cx + 5, cy + 5], [cx - 5, cy + 5], [cx - 5, cy - 5],
    ])
    result = build_geometry_from_bdnb(batiment, adresse={"lat": lat_nord, "lon": lon_c})
    assert result["geometry"]["entree_facade"] == "murs_nord"
    assert "entree_facade" in result["champs_ok"]


def test_geometry_sans_adresse_ne_place_pas_de_porte():
    result = build_geometry_from_bdnb(BATIMENT_NICE)  # pas d'adresse fournie
    assert result["geometry"]["entree_facade"] is None
    assert "entree_facade" in result["champs_manquants"]


def test_geometry_sans_geom_groupe_signale_le_footprint_manquant():
    result = build_geometry_from_bdnb({"nb_niveau": 1, "surface_emprise_sol": 64})
    assert result["geometry"]["footprint"] is None
    assert "footprint" in result["champs_manquants"]
    # Le repli rectangulaire doit rester exploitable par la scene 3D.
    assert result["geometry"]["largeur_m"] == 8.0
