"""Correctifs et adaptateurs du collector. Aucun acces reseau."""
import pytest

from risk_engine.collector_hardening import (
    AZI_POLICY, DATA_DICTIONARY_PROMISES, OBSERVED_DAILY_VARS,
    RECOMMENDED_DAILY_ADDITIONS, ClimateCache, ConcurrencyLimiter, RetryPolicy,
    availability_report, check_copernicus_config, check_wind_semantics,
    fwi_computable, inventory, paginate)
from risk_engine.canonical import Status


def test_inventory_flattens_real_payload(nice):
    inv = inventory(nice)
    assert "bdnb.batiment.alea_argile" in inv
    assert "georisques.zonage_sismique.data[0].code_zone" in inv
    assert "altitude_m" in inv


def test_availability_report_exposes_the_gap(nice):
    rep = availability_report(nice, DATA_DICTIONARY_PROMISES)
    # Les distances WFS annoncees au data dictionary sont absentes du JSON reel.
    assert rep["wfs_distances"]["coverage"] == 0.0
    # Les variables climatiques promises ne sont pas la non plus.
    assert rep["open_meteo_daily"]["coverage"] == 0.0
    # Georisques et BDNB sont en revanche largement presents.
    assert rep["georisques"]["coverage"] >= 0.75
    assert rep["bdnb"]["coverage"] == 1.0


def test_observed_daily_vars_are_only_two():
    assert set(OBSERVED_DAILY_VARS) == {"temperature_2m_max", "precipitation_sum"}
    assert "wind_speed_10m_max" in RECOMMENDED_DAILY_ADDITIONS
    assert "temperature_2m_min" in RECOMMENDED_DAILY_ADDITIONS


def test_wind_variable_is_never_labelled_gust():
    info = check_wind_semantics("wind_speed_10m_max")
    assert info["is_gust"] is False
    assert "rafale" in info["warning"].lower()
    assert check_wind_semantics("inconnue")["known"] is False


def test_fwi_not_computable_with_current_pipeline():
    res = fwi_computable({"temperature", "precipitation"})
    assert res["computable"] is False
    assert set(res["missing_inputs"]) == {"relative_humidity", "wind_speed"}
    assert "NON calcule" in res["decision"]


def test_fwi_still_blocked_when_inputs_present_but_conditions_undocumented():
    res = fwi_computable(set(["temperature", "relative_humidity",
                              "wind_speed", "precipitation"]))
    assert res["missing_inputs"] == []
    assert res["computable"] is False          # initialisation et convention horaire
    assert res["conditions"]["ffmc_dmc_dc_initialised"] is False


def test_pagination_is_complete(nice):
    pages = {
        1: {"results": 8, "total_pages": 2, "data": [{"i": i} for i in range(4)]},
        2: {"results": 8, "total_pages": 2, "data": [{"i": i} for i in range(4, 8)]},
    }
    out = paginate(lambda n: pages[n])
    assert out["records"] == 8
    assert out["pagination_complete"] is True


def test_pagination_reports_incompleteness():
    pages = {1: {"results": 83, "total_pages": 1, "data": [{"i": 0}]}}
    out = paginate(lambda n: pages[n])
    assert out["pagination_complete"] is False
    assert "1/83" in out["warning"]


def test_retry_respects_retry_after_and_backs_off():
    pol = RetryPolicy(seed=42)
    assert pol.delay_for(1, retry_after=30) == 30
    assert pol.delay_for(99, retry_after=9999) == pol.max_delay
    d1, d3 = pol.delay_for(1), pol.delay_for(3)
    assert d3 > d1                                  # croissance exponentielle
    assert pol.delay_for(1) == pol.delay_for(1)     # deterministe a graine fixee


def test_climate_cache_groups_addresses_of_same_cell():
    cache = ClimateCache(resolution_deg=0.25)
    cache.set(43.684164, 7.202467, {"ok": True})
    # Une adresse voisine tombe dans la meme maille : pas de nouvel appel.
    assert cache.get(43.69, 7.20) == {"ok": True}
    assert len(cache) == 1


def test_concurrency_limiter():
    lim = ConcurrencyLimiter(max_concurrent=2)
    assert lim.acquire() and lim.acquire()
    assert not lim.acquire()
    lim.release()
    assert lim.acquire()


def test_copernicus_config_validation():
    assert check_copernicus_config(None)["status"] == Status.NOT_CONFIGURED.value
    assert check_copernicus_config("~/.cdsapirc", None)["status"] == Status.NOT_CONFIGURED.value
    assert check_copernicus_config("~/.cdsapirc", "url: x\n")["status"] == Status.NOT_CONFIGURED.value
    ok = check_copernicus_config("~/.cdsapirc", "url: https://cds/api\nkey: abc\n")
    assert ok["status"] == "CONFIGURED"


def test_azi_policy_forbids_wrong_interpretation():
    assert AZI_POLICY["status_to_emit"] == Status.SOURCE_ERROR.value
    assert AZI_POLICY["forbidden_interpretation"] == "aucune zone inondable"
