"""
Test hors-ligne de bout en bout : POST /diagnostic -> collector_agent ->
scoring_agent -> digital_twin_agent -> contrat JSON, reseau mocke (meme
principe que test_collector_offline.py — voir sa docstring pour le detail
des limites reseau du sandbox de developpement).

Objectif : prouver que le graphe LangGraph complet et la route FastAPI
fonctionnent ensemble et produisent un contrat conforme au schema attendu
par `frontend/jumeau_numerique/index.html`, sans dependre d'un acces reseau
reel ni d'un vrai telechargement Copernicus.

A executer :
    PYTHONPATH=. python3 tests/test_api_diagnostic_offline.py
"""

from __future__ import annotations

import json
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
    if path.endswith(("/azi", "/cavites", "/zonage_sismique", "/radon", "/mvt")):
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

        with patch("app.agents.collector_agent.httpx.AsyncClient", side_effect=patched_client):
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

    print("test_diagnostic_end_to_end OK. Contrat :")
    print(json.dumps({k: v for k, v in contract.items() if not k.startswith("_")}, indent=2, ensure_ascii=False)[:1500], "...")


if __name__ == "__main__":
    test_diagnostic_end_to_end()
    print("\nTOUS LES TESTS test_api_diagnostic_offline PASSENT")
