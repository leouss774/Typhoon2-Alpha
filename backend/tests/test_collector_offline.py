"""
Test hors-ligne du collector_agent, sans acces reseau reel.

Le sandbox de developpement utilise pour ecrire ce projet n'autorise pas
les appels sortants vers les domaines publics (data.geopf.fr,
georisques.gouv.fr, api.bdnb.io, cds.climate.copernicus.eu, etc. sont tous
bloques par la politique reseau du bac a sable - verifie explicitement
avec curl -v, qui renvoie "403 blocked-by-allowlist"). Ce test ne peut donc
pas etre une verification "live" : il sert uniquement a prouver que la
logique d'assemblage (parsing des reponses, gestion des erreurs, procedure
BDNB en 2 etapes, extraction Copernicus au point le plus proche...) est
correcte, en simulant les reponses avec des payloads calques sur les
formats reels documentes par chaque fournisseur.

Ce test ne remplace JAMAIS un appel reel : le vrai test de bout en bout,
avec les vraies API et sans aucune donnee simulee, se fait via :
    python -m app.cli "10 Promenade des Anglais, 06000 Nice"
    python -m app.cli                      # mode interactif
    python -m app.cli --batch adresses_paca_exemple.txt

A executer (reseau reel requis) :
    pip install -r requirements.txt
    PYTHONPATH=. python3 tests/test_collector_offline.py
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import httpx
import numpy as np
import xarray as xr

from app.connectors import bdnb as bdnb_connector
from app.connectors import copernicus
from app.connectors import georisques as georisques_connector
from app.connectors import ign_altitude
from app.connectors import open_meteo
from app.connectors.geocoding import geocode_address
from app.core import config as core_config

GEOCODING_RESPONSE = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [7.2661, 43.6959]},
            "properties": {
                "label": "10 Promenade des Anglais 06000 Nice",
                "score": 0.93,
                "citycode": "06088",
                "postcode": "06000",
                "city": "Nice",
            },
        }
    ],
}

RESOURCES_RESPONSE = {
    "content": "1 resource",
    "resources": [{"_id": "ign_rge_alti_wld", "title": "RGE ALTI", "bbox": {}}],
}
ELEVATION_RESPONSE = {"elevations": [12.34]}

CLIMATE_RESPONSE_TEMPLATE = {
    "latitude": 43.7,
    "longitude": 7.27,
    "daily": {
        "time": ["2020-01-01", "2020-01-02", "2020-01-03"],
        "temperature_2m_max_EC_Earth3P_HR": [22.1, 36.4, 21.9],
        "temperature_2m_max_MRI_AGCM3_2_S": [23.0, 35.1, 22.4],
        "precipitation_sum_EC_Earth3P_HR": [0.0, 2.3, 0.0],
        "precipitation_sum_MRI_AGCM3_2_S": [0.1, 1.9, 0.0],
    },
}

GEORISQUES_RISQUES_RESPONSE = {"data": [{"libelle_risque_long": "Inondation"}]}
GEORISQUES_CATNAT_RESPONSE = {"data": []}

# Format observe pour le geocodeur BDNB : une liste de resultats, chacun
# avec un champ "id" = cle_interop_adr.
BDNB_GEOCODAGE_RESPONSE = [{"id": "06088_1234_00010", "label": "10 Promenade des Anglais 06000 Nice"}]
BDNB_BATIMENT_RESPONSE = [
    {
        "cle_interop_adr": "06088_1234_00010",
        "annee_construction": 1998,
        "materiau_structure": "beton",
        "nb_niveau": 2,
    }
]


def _mock_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path.endswith("/geocodage/search"):
        return httpx.Response(200, json=GEOCODING_RESPONSE)
    if path.endswith("/resources/"):
        return httpx.Response(200, json=RESOURCES_RESPONSE)
    if path.endswith("/elevation.json"):
        return httpx.Response(200, json=ELEVATION_RESPONSE)
    if path.endswith("/v1/climate"):
        return httpx.Response(200, json=CLIMATE_RESPONSE_TEMPLATE)
    if path.endswith("/gaspar/risques"):
        return httpx.Response(200, json=GEORISQUES_RISQUES_RESPONSE)
    if path.endswith("/gaspar/catnat"):
        return httpx.Response(200, json=GEORISQUES_CATNAT_RESPONSE)
    if path.endswith("/azi") or path.endswith("/cavites"):
        return httpx.Response(200, json={"data": []})
    if path.endswith("/zonage_sismique") or path.endswith("/radon") or path.endswith("/mvt"):
        return httpx.Response(404, json={"error": "not found"})
    if path.endswith("/v1/bdnb/geocodage"):
        return httpx.Response(200, json=BDNB_GEOCODAGE_RESPONSE)
    if path.endswith("/v1/bdnb/donnees/batiment_groupe_complet/adresse"):
        return httpx.Response(200, json=BDNB_BATIMENT_RESPONSE)
    raise AssertionError(f"URL non geree par le mock : {request.url}")


def _mock_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_mock_handler))


async def test_geocoding():
    async with _mock_client() as client:
        result = await geocode_address(client, "10 Promenade des Anglais, 06000 Nice")
    assert result.citycode == "06088"
    assert round(result.lat, 4) == 43.6959
    print("test_geocoding OK ->", result)


async def test_altitude():
    async with _mock_client() as client:
        alt = await ign_altitude.fetch_altitude(client, 43.6959, 7.2661)
    assert alt == 12.34
    print("test_altitude OK ->", alt)


async def test_climate_open_meteo():
    async with _mock_client() as client:
        summary = await open_meteo.fetch_climate_summary(client, 43.6959, 7.2661)
    assert summary.reference_2015_2024.jours_chaleur_extreme_par_an is not None
    print("test_climate_open_meteo OK ->", summary)


async def test_georisques_partial_failure():
    async with _mock_client() as client:
        data = await georisques_connector.fetch_georisques(client, "06088", 43.6959, 7.2661)
    assert data["risques_commune"] is not None
    assert data["zonage_sismique"] is None
    erreurs_sources = {e["source"] for e in data["erreurs"]}
    assert "georisques.zonage_sismique" in erreurs_sources
    print("test_georisques_partial_failure OK ->", json.dumps(data["erreurs"], ensure_ascii=False))


async def test_bdnb_geocodeur_format_geojson_feature():
    """Regression : sur une vraie adresse (26 Rue Victor Hugo, Bourgueil),
    le geocodeur BDNB a repondu avec un objet GeoJSON Feature unique
    (`properties.id`, pas de "id" au premier niveau) plutot que la liste
    plate simulee par BDNB_GEOCODAGE_RESPONSE ci-dessus. Avant le correctif
    de `_geocode_bdnb`, ce format faisait planter la collecte -> bdnb
    restait a None pour toute adresse ou l'API repond sous cette forme."""
    geojson_feature_response = {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [0.169251, 47.283669]},
        "properties": {
            "id": "37031_1591_00026",
            "label": "26 Rue Victor Hugo 37140 Bourgueil",
            "citycode": "37031",
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v1/bdnb/geocodage"):
            return httpx.Response(200, json=geojson_feature_response)
        if request.url.path.endswith("/v1/bdnb/donnees/batiment_groupe_complet/adresse"):
            return httpx.Response(200, json=[{"cle_interop_adr": "37031_1591_00026", "nb_niveau": 2}])
        raise AssertionError(f"URL non geree : {request.url}")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await bdnb_connector.fetch_bdnb(client, "26 Rue Victor Hugo, 37140 Bourgueil")
    assert result["cle_interop_adr"] == "37031_1591_00026"
    print("test_bdnb_geocodeur_format_geojson_feature OK ->", result)


async def test_bdnb_deux_etapes():
    """Verifie la procedure BDNB en 2 appels : geocodage -> cle_interop_adr,
    puis donnees/batiment_groupe_complet/adresse avec cette cle exacte.
    Aucune cle API n'est necessaire (confirme par un test reel : l'offre
    Open de BDNB repond sans en-tete Authorization)."""
    core_config.settings.bdnb_api_key = None
    async with _mock_client() as client:
        result = await bdnb_connector.fetch_bdnb(client, "10 Promenade des Anglais, 06000 Nice")
    assert result["cle_interop_adr"] == "06088_1234_00010"
    assert result["batiment"]["materiau_structure"] == "beton"
    print("test_bdnb_deux_etapes OK ->", result)


def test_copernicus_refuse_sans_configuration():
    """Si _REQUEST est vide (ex. quelqu'un l'a efface par erreur), le
    connecteur doit refuser d'inventer une valeur plutot que de planter
    silencieusement ou de renvoyer un resultat fabrique."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        core_config.settings.copernicus_cache_dir = tmp_dir
        with patch.object(copernicus, "_REQUEST", {}):
            try:
                copernicus.ensure_dataset_downloaded()
                raise AssertionError("Aurait du lever CopernicusNotConfigured")
            except copernicus.CopernicusNotConfigured as exc:
                print("test_copernicus_refuse_sans_configuration OK ->", exc)


def test_copernicus_request_est_bien_celle_fournie():
    """Garde-fou anti-regression : verifie que _REQUEST correspond
    exactement a la requete communiquee (aucun champ invente ou oublie)."""
    assert copernicus._REQUEST["origin"] == "projections"
    assert copernicus._REQUEST["gcm"] == ["ipsl_cm5a_mr"]
    assert copernicus._REQUEST["rcm"] == ["wrf381p"]
    assert set(copernicus._REQUEST["experiment"]) == {"rcp4_5", "rcp8_5"}
    assert "hot_days" in copernicus._REQUEST["variable"]
    assert "magnitude_of_meteorological_droughts" in copernicus._REQUEST["variable"]
    print("test_copernicus_request_est_bien_celle_fournie OK")


def test_copernicus_extraction_point_fichier_unique():
    """Verifie l'extraction au point le plus proche sur un NetCDF factice
    (structure calquee sur le vrai dataset : grille lat/lon + variables),
    sans jamais passer par un vrai telechargement CDS."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        core_config.settings.copernicus_cache_dir = tmp_dir
        (cache_dir / ".download_complete").write_text("ok")

        lats = np.array([42.9, 43.2, 43.7, 45.5])
        lons = np.array([4.5, 6.0, 7.27, 7.7])
        heatwave_days = xr.DataArray(
            np.arange(len(lats) * len(lons)).reshape(len(lats), len(lons)),
            coords={"latitude": lats, "longitude": lons},
            dims=["latitude", "longitude"],
        )
        xr.Dataset({"heatwave_days": heatwave_days}).to_netcdf(cache_dir / "rcp4_5_yearly.nc")

        result = copernicus.read_indicators_at_point(43.6959, 7.2661)

    assert "rcp4_5_yearly__heatwave_days" in result
    print("test_copernicus_extraction_point_fichier_unique OK ->", result)


async def test_full_collect_pipeline():
    """Verifie collector_agent.collect() de bout en bout, reseau mocke.

    Pour Copernicus, on pre-remplit le cache local (marqueur + faux NetCDF)
    comme si un vrai telechargement CDS avait deja eu lieu : cela permet de
    tester le vrai code de lecture/extraction sans jamais instancier
    cdsapi.Client() (qui, dans cet environnement sans reseau, resterait
    bloque en boucle de nouvelle tentative - voir docstring de
    copernicus.py). Le fichier NetCDF lui-meme reste factice ; ce n'est
    pas presente comme une donnee climatique reelle.
    """
    from app.agents import collector_agent

    real_async_client = httpx.AsyncClient

    def patched_client(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(_mock_handler)
        return real_async_client(*args, **kwargs)

    core_config.settings.bdnb_api_key = None  # aucune cle necessaire

    with tempfile.TemporaryDirectory() as tmp_dir:
        cache_dir = Path(tmp_dir)
        core_config.settings.copernicus_cache_dir = tmp_dir
        (cache_dir / ".download_complete").write_text("ok")
        lats = np.array([42.9, 45.5])
        lons = np.array([4.5, 7.7])
        fake_var = xr.DataArray(
            np.arange(4).reshape(2, 2),
            coords={"latitude": lats, "longitude": lons},
            dims=["latitude", "longitude"],
        )
        xr.Dataset({"heatwave_days": fake_var}).to_netcdf(cache_dir / "rcp4_5_yearly.nc")

        with patch("app.agents.collector_agent.httpx.AsyncClient", side_effect=patched_client):
            building_data = await collector_agent.collect("10 Promenade des Anglais, 06000 Nice")

    assert building_data["adresse"]["citycode"] == "06088"
    assert building_data["dans_perimetre_paca"] is True
    assert building_data["altitude_m"] == 12.34
    assert building_data["bdnb"]["cle_interop_adr"] == "06088_1234_00010"
    assert building_data["georisques"]["risques_commune"] is not None
    assert building_data["climat_open_meteo"]["reference_2015_2024"]["temperature_max_moyenne_c"] is not None
    assert "rcp4_5_yearly__heatwave_days" in building_data["climat_copernicus"]
    erreurs_sources = {e["source"] for e in building_data["erreurs"]}
    assert "dvf_local" in erreurs_sources  # aucun CSV DVF telecharge dans ce test
    assert "copernicus" not in erreurs_sources
    print("\ntest_full_collect_pipeline OK. Extrait :")
    print(json.dumps(building_data, indent=2, ensure_ascii=False)[:1200], "...")


async def _run_all():
    await test_geocoding()
    await test_altitude()
    await test_climate_open_meteo()
    await test_georisques_partial_failure()
    await test_bdnb_geocodeur_format_geojson_feature()
    await test_bdnb_deux_etapes()
    test_copernicus_refuse_sans_configuration()
    test_copernicus_request_est_bien_celle_fournie()
    test_copernicus_extraction_point_fichier_unique()
    await test_full_collect_pipeline()
    print("\nTOUS LES TESTS HORS-LIGNE PASSENT")


if __name__ == "__main__":
    asyncio.run(_run_all())
