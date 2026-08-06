"""
Test hors-ligne de bout en bout : POST /diagnostic -> collector_agent ->
scoring_agent -> recommandations_agent -> digital_twin_agent -> contrat
JSON, reseau mocke (meme principe que test_collector_offline.py — voir sa
docstring pour le detail des limites reseau du sandbox de developpement).

Objectif : prouver que le graphe LangGraph complet (recommandations_agent
inclus, cf. backend/recommendation_travaux-main/PROMPT_INTEGRATION_ouss.md)
et la route FastAPI fonctionnent ensemble et produisent un contrat conforme
au schema attendu par `frontend/jumeau_numerique/index.html`, sans dependre
d'un acces reseau reel (ni Copernicus, ni Mistral) ni de credits API.

Les appels Mistral (embeddings + chat) du noeud recommandations_agent sont
mockes ici : `app.recommandations.service.embed_texts` (utilise par
`search_zone_candidates`) et `app.agents.recommandations_agent.chat_json`
(l'agent importe chat_json directement depuis mistral_client et l'appelle
via `asyncio.to_thread`) : ce test verifie que le noeud est bien branche et
alimente `zones[*].recommandations`, pas que le RAG Mistral reel fonctionne
(pour ca, voir les commandes de test manuel avec un vrai POST /diagnostic).

A executer :
    PYTHONPATH=. python3 tests/test_api_diagnostic_offline.py
"""

from __future__ import annotations

import json
import struct
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
import xarray as xr

ZONE_NAMES = ["fondations", "murs_nord", "murs_sud", "murs_est", "murs_ouest", "toiture", "sous_sol"]

# Reponses calquees sur un vrai test (26 Rue Victor Hugo, 37140 Bourgueil) :
# geocodeur BDNB en GeoJSON Feature (cf. test_bdnb_geocodeur_format_geojson_feature),
# Georisques avec un vrai historique CATNAT inondation/secheresse.
GEOCODING_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0.169251, 47.283669]},
            "properties": {
                "label": "26 Rue Victor Hugo 37140 Bourgueil",
                "score": 0.958,
                "citycode": "37031",
                "postcode": "37140",
                "city": "Bourgueil",
            },
        }
    ],
}
RESOURCES_RESPONSE = {"content": "1 resource", "resources": [{"_id": "ign_rge_alti_wld"}]}
ELEVATION_RESPONSE = {"elevations": [45.0]}
CLIMATE_RESPONSE = {
    "latitude": 47.28, "longitude": 0.17,
    "daily": {
        "time": ["2020-01-01", "2020-01-02"],
        "temperature_2m_max_EC_Earth3P_HR": [16.0, 18.0],
        "temperature_2m_max_MRI_AGCM3_2_S": [17.0, 19.0],
        "precipitation_sum_EC_Earth3P_HR": [0.0, 2.0],
        "precipitation_sum_MRI_AGCM3_2_S": [0.0, 1.5],
    },
}
BDNB_GEOCODAGE_FEATURE = {
    "type": "Feature",
    "properties": {"id": "37031_1591_00026", "label": "26 Rue Victor Hugo 37140 Bourgueil"},
}
BDNB_BATIMENT_ROWS = [
    {
        "cle_interop_adr": "37031_1591_00026",
        "annee_construction": 1850,
        "nb_niveau": 2,
        "hauteur_mean": 5,
        "mat_mur_txt": "MEULIERE",
        "mat_toit_txt": "ARDOISES",
        "alea_argile": "Moyen",
        "surface_emprise_sol": 155,
        "usage_niveau_1_txt": "Résidentiel individuel",
        "geom_groupe": {
            "type": "MultiPolygon",
            "coordinates": [[[[486107, 6690878.5], [486101.5, 6690859.8], [486095.6, 6690862.7], [486107, 6690878.5]]]],
        },
    }
]
GEORISQUES_RISQUES = {"data": [{"risques_detail": [{"libelle_risque_long": "Inondation", "zone_sismicite": 2}]}]}
GEORISQUES_CATNAT = {
    "data": [
        {"libelle_risque_jo": "Inondations et/ou Coulées de Boue"},
        {"libelle_risque_jo": "Inondations et/ou Coulées de Boue"},
        {"libelle_risque_jo": "Sécheresse"},
    ]
}

# --- Mocks Mistral (agent recommandations, cf. app/recommandations/) ---
# embed_texts : vecteur bidon de la bonne dimension (1024, cf.
# app/recommandations/data/index.json) -- la recherche par similarite
# cosinus tourne reellement contre l'index reel, seul l'appel reseau
# Mistral est evite. chat_json : reponse fixe plutot qu'un vrai appel LLM.
def _fake_embed_texts(texts):
    return [[0.01] * 1024 for _ in texts]


def _fake_chat_json(system_prompt, user_prompt):
    return {
        "recommandations": [
            {
                "mesure": "[TEST] mesure de reduction de vulnerabilite",
                "explication": "[TEST] explication detaillee de la mesure et de son lien avec le risque.",
                "type": "recommandation_source",
                "cout_estime": None,
                "aide": None,
                "sources": [{"fiche_id": "test", "source_id": "S00", "extrait_exact": "..."}],
            }
        ]
    }


def _mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/geocodage/search"):
        return httpx.Response(200, json=GEOCODING_RESPONSE)
    if path.endswith("/resources/"):
        return httpx.Response(200, json=RESOURCES_RESPONSE)
    if path.endswith("/elevation.json"):
        return httpx.Response(200, json=ELEVATION_RESPONSE)
    if path.endswith("/v1/climate"):
        return httpx.Response(200, json=CLIMATE_RESPONSE)
    if path.endswith("/gaspar/risques"):
        return httpx.Response(200, json=GEORISQUES_RISQUES)
    if path.endswith("/gaspar/catnat"):
        return httpx.Response(200, json=GEORISQUES_CATNAT)
    if path.endswith(
        (
            "/azi",
            "/cavites",
            "/zonage_sismique",
            "/radon",
            "/mvt",
            "/pprn",
            "/pprt",
            "/ssp",
            "/installations_classees",
        )
    ):
        return httpx.Response(200, json={"data": []})
    if path.endswith("/v1/bdnb/geocodage"):
        return httpx.Response(200, json=BDNB_GEOCODAGE_FEATURE)
    if path.endswith("/v1/bdnb/donnees/batiment_groupe_complet/adresse"):
        return httpx.Response(200, json=BDNB_BATIMENT_ROWS)
    raise AssertionError(f"URL non geree par le mock : {request.url}")


def test_diagnostic_end_to_end():
    from app.core import config as core_config

    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        core_config.settings.copernicus_cache_dir = tmp_dir
        core_config.settings.bdnb_api_key = None
        (cache_dir / ".download_complete").write_text("ok")
        lats, lons = np.array([46.0, 48.0]), np.array([-1.0, 1.0])
        fake_var = xr.DataArray(np.arange(4).reshape(2, 2), coords={"latitude": lats, "longitude": lons}, dims=["latitude", "longitude"])
        xr.Dataset({"heatwave_days": fake_var}).to_netcdf(cache_dir / "rcp4_5_yearly.nc")

        real_async_client = httpx.AsyncClient

        def patched_client(*args, **kwargs):
            kwargs["transport"] = httpx.MockTransport(_mock_handler)
            return real_async_client(*args, **kwargs)

        with patch("app.agents.collector_agent.httpx.AsyncClient", side_effect=patched_client), \
             patch("app.recommandations.service.embed_texts", side_effect=_fake_embed_texts), \
             patch("app.agents.recommandations_agent.chat_json", side_effect=_fake_chat_json):
            from app.main import app
            from fastapi.testclient import TestClient

            with TestClient(app) as client:
                response = client.post("/diagnostic", json={"adresse": "26 Rue Victor Hugo, 37140 Bourgueil"})

    assert response.status_code == 200, response.text
    contract = response.json()

    # --- forme du contrat attendue par frontend/jumeau_numerique/index.html ---
    assert contract["adresse"] == "26 Rue Victor Hugo 37140 Bourgueil"
    assert set(contract["zones"].keys()) == set(ZONE_NAMES)
    assert set(contract["projection_2050"]["zones"].keys()) == set(ZONE_NAMES)
    assert isinstance(contract["score_global"], int)
    assert 0 <= contract["score_global"] <= 100
    for zone in ZONE_NAMES:
        z = contract["zones"][zone]
        assert set(z.keys()) >= {"risque", "niveau", "alea_principal", "justification", "recommandations"}
        assert 0 <= z["risque"] <= 100

    geometry = contract["geometry"]
    assert geometry["largeur_m"] > 0 and geometry["longueur_m"] > 0
    assert geometry["floors_count"] == 2
    assert geometry["materiau_mur"] == "meuliere"
    assert isinstance(geometry["has_basement"], bool)  # jamais None cote front

    # le score fondations doit refleter l'alea argile "Moyen" fourni par la BDNB
    assert "argile" in contract["zones"]["fondations"]["justification"].lower()
    # le score sous_sol doit refleter les 2 arretes CATNAT inondation mockes
    assert "inondation" in contract["zones"]["sous_sol"]["justification"].lower()

    # --- recommandations_agent (nouveau noeud) : verifie que le contrat
    # contient bien des recommandations sourcees pour les zones a risque
    # non-faible (fondations, sous_sol -- cf. calcul risk_model ci-dessus),
    # sans avoir appele le vrai Mistral (mocke plus haut).
    for zone in ("fondations", "sous_sol"):
        recos = contract["zones"][zone]["recommandations"]
        assert recos, f"zone {zone} : aucune recommandation (noeud recommandations_agent non branche ?)"
        assert recos[0]["mesure"] == "[TEST] mesure de reduction de vulnerabilite"

    print("test_diagnostic_end_to_end OK. Contrat :")
    print(json.dumps({k: v for k, v in contract.items() if not k.startswith("_")}, indent=2, ensure_ascii=False)[:1500], "...")


def test_diagnostic_adresse_gltf():
    """GET /diagnostic/adresse/gltf : .glb valide (magic glTF) genere depuis
    l'emprise BDNB, reseau mocke (geocodeur IGN + geocodeur BDNB + fiche
    batiment)."""
    from app.main import app
    from fastapi.testclient import TestClient

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_mock_handler)
        return real_async_client(*args, **kwargs)

    with patch(
        "app.api.routes.diagnostic.httpx.AsyncClient", side_effect=patched_client
    ):
        with TestClient(app) as client:
            resp = client.get(
                "/diagnostic/adresse/gltf",
                params={"q": "26 Rue Victor Hugo, 37140 Bourgueil"},
            )

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("model/gltf-binary")

    body = resp.content
    magic, version, total = struct.unpack("<III", body[:12])
    assert magic == 0x46546C67, "magic 'glTF' manquant"
    assert version == 2
    assert total == len(body), "longueur totale .glb incohérente"

    # Le chunk JSON doit etre padde avec des espaces (spec glTF) : JSON.parse
    # doit pouvoir le lire tel quel (les parsers stricts rejettent \x00).
    json_len, json_type = struct.unpack("<II", body[12:20])
    assert json_type == 0x4E4F534A
    json.loads(body[20 : 20 + json_len].decode("utf-8"))


def test_gltf_builder_utilise_lemprise_bdnb_reelle():
    """build_glb_from_bdnb doit extruser le polygone reel (`exterieur`,
    convention footprint.py) et non retomber sur la boite 10x10x6.

    Le triangle Lambert-93 de BDNB_BATIMENT_ROWS s'etend sur ~11 m x ~19 m
    autour de son centroide : une boite de secours aurait une emprise exacte
    de 10 m (min/max a +/- 5 m sur X et Z).
    """
    from app.digital_twin.gltf_builder import build_glb_from_bdnb

    glb = build_glb_from_bdnb(BDNB_BATIMENT_ROWS[0], adresse_label="test")
    assert glb is not None

    json_len, _ = struct.unpack("<II", glb[12:20])
    doc = json.loads(glb[20 : 20 + json_len].decode("utf-8"))
    positions = next(a for a in doc["accessors"] if a["type"] == "VEC3")
    pos_min, pos_max = positions["min"], positions["max"]

    # Emprise reelle : depasse +/- 5 m (pas la boite 10x10x6 de repli)
    assert pos_max[2] > 5.0, f"emprise non reelle (max z={pos_max[2]}) — repli boite ?"
    assert pos_max[0] > 5.0, f"emprise non reelle (max x={pos_max[0]}) — repli boite ?"


def test_gltf_builder_faces_orientees_vers_lexterieur():
    """Chaque triangle du .glb doit avoir sa normale tournee vers
    l'exterieur du volume (regression : le winding en (x, z) donnait des
    normales -y, soit 0/12 faces visibles avec doubleSided=false — le
    batiment rendu etait translucide).
    """
    from app.digital_twin.gltf_builder import build_glb

    glb = build_glb([(0.0, 0.0), (10.0, 0.0), (10.0, 8.0), (0.0, 8.0)], height_m=7.0)
    json_len, _ = struct.unpack("<II", glb[12:20])
    doc = json.loads(glb[20 : 20 + json_len].decode("utf-8"))
    bin_len, _ = struct.unpack("<II", glb[20 + json_len : 28 + json_len])
    bin_data = glb[28 + json_len : 28 + json_len + bin_len]

    idx_acc = next(a for a in doc["accessors"] if a["type"] == "SCALAR")
    pos_acc = next(a for a in doc["accessors"] if a["type"] == "VEC3")
    idx_view = doc["bufferViews"][idx_acc["bufferView"]]
    pos_view = doc["bufferViews"][pos_acc["bufferView"]]

    indices = struct.unpack_from(
        "<%dH" % idx_acc["count"], bin_data, idx_view["byteOffset"]
    )
    positions = struct.unpack_from(
        "<%df" % (pos_acc["count"] * 3), bin_data, pos_view["byteOffset"]
    )

    def pt(i):
        return positions[i * 3 : i * 3 + 3]

    centroid = (5.0, 3.5, 4.0)  # centre du parallelepipede [0,10]x[0,7]x[0,8]
    outward = 0
    for t in range(0, len(indices), 3):
        p0, p1, p2 = pt(indices[t]), pt(indices[t + 1]), pt(indices[t + 2])
        u = (p1[0] - p0[0], p1[1] - p0[1], p1[2] - p0[2])
        v = (p2[0] - p0[0], p2[1] - p0[1], p2[2] - p0[2])
        n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
        fc = ((p0[0] + p1[0] + p2[0]) / 3, (p0[1] + p1[1] + p2[1]) / 3, (p0[2] + p1[2] + p2[2]) / 3)
        if n[0] * (fc[0] - centroid[0]) + n[1] * (fc[1] - centroid[1]) + n[2] * (fc[2] - centroid[2]) > 0:
            outward += 1

    n_faces = len(indices) // 3
    assert n_faces == 12
    assert outward == n_faces, f"{outward}/{n_faces} faces vers l'exterieur"


def test_gltf_builder_bim_multimateriaux_et_toiture_pentue():
    """build_glb_bim : 3 primitives (murs/toiture/planchers), toit pentu
    (sommets au-dessus de l'avant-toit), planchers par niveau."""
    from app.digital_twin.gltf_builder import build_glb_bim

    polygones = [
        {"exterieur": [[0.0, 0.0], [20.0, 0.0], [20.0, 10.0], [0.0, 10.0]], "trous": []}
    ]
    glb = build_glb_bim(
        polygones,
        hauteur_m=8.0,
        label="test",
        mat_mur="BETON",
        mat_toit="ARDOISES",
        floors=3,
        pente_toit_deg=42.0,
        ridge_axis_deg=0.0,
    )
    assert glb is not None
    json_len, _ = struct.unpack("<II", glb[12:20])
    doc = json.loads(glb[20 : 20 + json_len].decode("utf-8"))

    names = [m["name"] for m in doc["materials"]]
    assert names == ["Murs", "Toiture", "Planchers", "Sol"]

    prims = doc["meshes"][0]["primitives"]
    assert len(prims) == 4

    def positions_of(prim_idx: int):
        pos = doc["accessors"][prims[prim_idx]["attributes"]["POSITION"]]
        return pos["min"], pos["max"]

    # Murs : hauteur avant-toit comprise entre 0 et la hauteur totale
    # (toit 42° sur 10 m de large → avant-toit ~3.6 m pour 8 m)
    mur_min, mur_max = positions_of(0)
    assert mur_max[1] < 8.0
    assert mur_max[1] > 2.5  # murs suffisamment hauts

    # Toiture : sommets plus hauts que l'avant-toit (faîtage > eave)
    toit_min, toit_max = positions_of(1)
    assert toit_max[1] > mur_max[1] + 1.0, "toit non pentu"
    assert toit_max[1] <= 8.0 + 1e-6

    # Planchers : un par niveau, bornés sous l'avant-toit. La dalle du RDC
    # est posée à +3 cm (anti z-fighting avec le sol du .glb et l'herbe du
    # viewer), les suivantes à k × hauteur_niveau.
    slab_min, slab_max = positions_of(2)
    assert abs(slab_min[1] - 0.03) < 1e-6
    assert slab_max[1] < mur_max[1] + 1e-6  # aucun plancher au-dessus des murs
    assert slab_max[1] > 2.5  # plusieurs niveaux présents

    # Matériau BDNB "BETON" → texture murale embarquée : baseColorTexture
    # présent, facteur au blanc (le facteur MULTIPLIE la texture en glTF),
    # image + TEXCOORD_0 dans le document.
    murs_pbr = doc["materials"][0]["pbrMetallicRoughness"]
    assert "baseColorTexture" in murs_pbr, "texture murale absente pour BETON"
    assert murs_pbr["baseColorFactor"] == [1.0, 1.0, 1.0, 1.0]
    assert doc.get("images"), "image de texture non embarquée"
    assert doc.get("textures"), "table textures absente"
    assert "TEXCOORD_0" in prims[0]["attributes"], "UV absents sur les murs"
    # La toiture ARDOISES est texturée elle aussi (toit_ardoises.jpg).
    assert "baseColorTexture" in doc["materials"][1]["pbrMetallicRoughness"]


def test_gltf_builder_bim_fenetres_et_porte():
    """Fenetres sur les facades vitrees (DPE) + porte d'entree cote rue :
    primitives vitrage/cadres/porte presentes, vitrage translucide
    (alphaMode BLEND), porte posee au sol sur la facade demandee, et
    entree_facade estimee depuis le point d'adresse dans build_glb_from_bdnb.
    """
    from app.digital_twin.gltf_builder import build_glb_bim, build_glb_from_bdnb

    polygones = [
        {"exterieur": [[0.0, 0.0], [20.0, 0.0], [20.0, 10.0], [0.0, 10.0]], "trous": []}
    ]
    glb = build_glb_bim(
        polygones,
        hauteur_m=8.0,
        label="test",
        floors=3,
        pente_toit_deg=42.0,
        ridge_axis_deg=0.0,
        facades_avec_vitrage=["murs_est", "murs_ouest", "murs_nord"],
        ratio_vitrage=0.15,
        entree_facade="murs_sud",
    )
    assert glb is not None
    json_len, _ = struct.unpack("<II", glb[12:20])
    doc = json.loads(glb[20 : 20 + json_len].decode("utf-8"))

    names = [m["name"] for m in doc["materials"]]
    assert names == ["Murs", "Toiture", "Planchers", "Cadres", "Vitrage", "Porte", "Sol"]

    prims = doc["meshes"][0]["primitives"]
    assert len(prims) == 7

    # Vitrage translucide (alphaMode BLEND) et double face
    vitrage_mat = doc["materials"][4]
    assert vitrage_mat.get("alphaMode") == "BLEND"
    assert vitrage_mat["doubleSided"] is True

    # Les 3 nouvelles primitives ont de la geometrie
    for i, name in ((3, "Cadres"), (4, "Vitrage"), (5, "Porte")):
        pos = doc["accessors"][prims[i]["attributes"]["POSITION"]]
        assert pos["count"] > 0, f"{name} sans geometrie"

    # La porte est posee au sol, haute de ~2.3 m, sur la facade sud (z > 0)
    porte_min = doc["accessors"][prims[5]["attributes"]["POSITION"]]["min"]
    porte_max = doc["accessors"][prims[5]["attributes"]["POSITION"]]["max"]
    assert abs(porte_min[1]) < 1e-6, "porte non posee sur le sol"
    assert porte_max[1] <= 2.4 + 1e-6, f"porte trop haute ({porte_max[1]})"
    assert porte_min[2] > 5.0, f"porte pas sur la facade sud (z_min={porte_min[2]})"

    # Les fenetres sont sur les facades EST/OUEST/NORD : du verre est present
    # hors du plan z > 9.9 (la facade sud porte la porte, pas de vitrage)
    vitrage_pos = doc["accessors"][prims[4]["attributes"]["POSITION"]]
    assert vitrage_pos["max"][2] < 9.9 + 1e-6, "vitrage present sur la facade sud"
    assert vitrage_pos["min"][2] < -0.04 + 1e-6, "vitrage absent de la facade nord"

    # --- Integration : entree_facade estimee depuis le point d'adresse ---
    # (batiment fictif BDNB + point d'adresse ~150 m a l'est du centroide
    # Lambert-93 -> la porte doit atterrir sur murs_est)
    from app.digital_twin.footprint import lambert93_to_wgs84

    batiment = dict(BDNB_BATIMENT_ROWS[0])
    batiment.update(
        {
            "l_orientation_baie_vitree": ["est", "nord", "ouest", "sud"],
            "pourcentage_surface_baie_vitree_exterieur": 15.5,
        }
    )
    lat_c, lon_c = lambert93_to_wgs84(486101.36666667, 6690867.0)
    glb2 = build_glb_from_bdnb(
        batiment, adresse_lat=lat_c + 0.0001, adresse_lon=lon_c + 0.002
    )
    assert glb2 is not None
    json_len2, _ = struct.unpack("<II", glb2[12:20])
    doc2 = json.loads(glb2[20 : 20 + json_len2].decode("utf-8"))
    names2 = [m["name"] for m in doc2["materials"]]
    assert names2 == ["Murs", "Toiture", "Planchers", "Cadres", "Vitrage", "Porte", "Sol"]
    prims2 = doc2["meshes"][0]["primitives"]
    porte_pos = doc2["accessors"][prims2[5]["attributes"]["POSITION"]]
    assert porte_pos["count"] > 0, "porte absente malgre un point d'adresse fourni"

    # --- La porte est INDEPENDANTE du vitrage DPE : un batiment sans donnees
    # de baies vitrees (couverture DPE partielle) garde sa porte cote rue.
    glb3 = build_glb_bim(
        polygones,
        hauteur_m=8.0,
        label="test",
        floors=3,
        entree_facade="murs_sud",
    )
    assert glb3 is not None
    json_len3, _ = struct.unpack("<II", glb3[12:20])
    doc3 = json.loads(glb3[20 : 20 + json_len3].decode("utf-8"))
    names3 = [m["name"] for m in doc3["materials"]]
    # Pas de Vitrage (mais Cadres = le cadre de la porte est une menuiserie),
    # la porte presente, et le Sol toujours en derniere position
    assert names3 == ["Murs", "Toiture", "Planchers", "Cadres", "Porte", "Sol"]
    prims3 = doc3["meshes"][0]["primitives"]
    porte3 = doc3["accessors"][prims3[names3.index("Porte")]["attributes"]["POSITION"]]
    assert porte3["count"] > 0, "porte absente sans donnees de vitrage"
    assert not any(m["name"] == "Vitrage" for m in doc3["materials"])


def test_gltf_builder_bim_trou_cour_interieure():
    """Un trou (cour intérieure) dans l'emprise : la surface triangulée des
    planchers vaut exterieur - trou, et aucun triangle n'empiète sur la cour
    (régression du bridge-cut : le pont doit être visible, sinon chevauchement)."""
    from app.digital_twin.gltf_builder import (
        _cross_2d,
        _point_in_ring_2d,
        _triangulate_polygon_with_holes,
    )

    ext = [[0.0, 0.0], [20.0, 0.0], [20.0, 10.0], [0.0, 10.0]]
    trou = [[6.0, 3.0], [6.0, 7.0], [10.0, 7.0], [10.0, 3.0]]
    ring, tris = _triangulate_polygon_with_holes(ext, [trou])

    area = sum(abs(_cross_2d(ring[a], ring[b], ring[c])) / 2 for a, b, c in tris)
    assert abs(area - 184.0) < 1.0, f"aire {area} != 184"

    for a, b, c in tris:
        cx = (ring[a][0] + ring[b][0] + ring[c][0]) / 3
        cy = (ring[a][1] + ring[b][1] + ring[c][1]) / 3
        assert not _point_in_ring_2d((cx, cy), trou), "triangle dans la cour"


def test_gltf_builder_bim_deux_trous():
    """Deux cours intérieures : aire = exterieur - trou1 - trou2."""
    from app.digital_twin.gltf_builder import _cross_2d, _triangulate_polygon_with_holes

    ext = [[0.0, 0.0], [30.0, 0.0], [30.0, 20.0], [0.0, 20.0]]
    t1 = [[3.0, 3.0], [3.0, 6.0], [6.0, 6.0], [6.0, 3.0]]
    t2 = [[24.0, 14.0], [24.0, 17.0], [27.0, 17.0], [27.0, 14.0]]
    ring, tris = _triangulate_polygon_with_holes(ext, [t1, t2])
    area = sum(abs(_cross_2d(ring[a], ring[b], ring[c])) / 2 for a, b, c in tris)
    assert abs(area - 582.0) < 1.0, f"aire {area} != 582"


def test_rapport_narratif_erreurs_contractees():
    """POST /diagnostic/adresse/rapport : le contrat d'erreur est structure —
    (error, detail, cause) — et distingue clé API manquante (503) d'un échec
    Mistral (502 avec la cause technique transmise, plus de message générique
    vide). Le code d'erreur standard FastAPI est détourné en détail JSON."""
    from app.main import app
    from fastapi.testclient import TestClient
    from app.core.config import settings

    report = {
        "adresse_saisie": "26 Rue Victor Hugo, 37140 Bourgueil",
        "adresse_normalisee": "26 Rue Victor Hugo 37140 Bourgueil",
        "lat": 47.283669,
        "lon": 0.169251,
        "code_insee": "37031",
        "date_generation": "2026-01-01",
        "alea_count": 1,
        "aleas": [
            {"code": "inondation", "libelle": "Inondation", "present": True, "niveau": None}
        ],
        "erreurs_partielles": [],
    }

    real_key = settings.mistral_api_key
    try:
        # 1) Pas de clé API → 503 mistral_api_key_manquante, cause explicite
        settings.mistral_api_key = None
        with TestClient(app) as client:
            resp = client.post("/diagnostic/adresse/rapport", json=report)
        assert resp.status_code == 503
        body = resp.json()["detail"]
        assert body["error"] == "mistral_api_key_manquante"
        assert "MISTRAL_API_KEY" in body["detail"]
        assert body["cause"]

        # 2) Clé présente mais Mistral en échec → 502 avec cause technique
        #    (chat_json est importé localement par rapport_narratif : on patche
        #    donc la source dans mistral_client)
        settings.mistral_api_key = "test-key"
        with patch(
            "app.recommandations.mistral_client.chat_json",
            side_effect=RuntimeError("429 rate limit exceeded"),
        ):
            with TestClient(app) as client:
                resp = client.post("/diagnostic/adresse/rapport", json=report)
        assert resp.status_code == 502
        body = resp.json()["detail"]
        assert body["error"] == "mistral_indisponible"
        assert body["detail"]  # message utilisateur non vide
        assert "429" in body["cause"], body["cause"]  # cause technique transmise
    finally:
        settings.mistral_api_key = real_key


if __name__ == "__main__":
    test_diagnostic_end_to_end()
    test_diagnostic_adresse_gltf()
    test_gltf_builder_utilise_lemprise_bdnb_reelle()
    test_gltf_builder_faces_orientees_vers_lexterieur()
    test_gltf_builder_bim_fenetres_et_porte()
    test_rapport_narratif_erreurs_contractees()
    print("\nTOUS LES TESTS test_api_diagnostic_offline PASSENT")
