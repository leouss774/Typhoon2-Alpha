"""Non-regression sur le cas reel de Nice (73 av. Simone Veil, 06088)."""
import json
import re
from pathlib import Path

import pytest

from risk_engine.engine import PerilStatus, assess
from risk_engine.questionnaire import build_questionnaire

ROOT = Path(__file__).resolve().parent.parent

#: Statuts attendus SANS aucune reponse utilisateur.
EXPECTED_NO_ANSWERS = {
    "P01": PerilStatus.INDETERMINATE,
    "P02": PerilStatus.NEEDS_USER_INPUT,
    "P03": PerilStatus.CALCULATED,
    "P04-CAV": PerilStatus.INDETERMINATE,
    "P04-GLI": PerilStatus.INDETERMINATE,
    "P04-BLO": PerilStatus.NEEDS_USER_INPUT,
    "P04-TAS": PerilStatus.NEEDS_USER_INPUT,
    "P05": PerilStatus.INDETERMINATE,
    "P06": PerilStatus.NEEDS_USER_INPUT,
    "P07": PerilStatus.NEEDS_USER_INPUT,
    "P08": PerilStatus.NEEDS_USER_INPUT,
    "P09": PerilStatus.INDETERMINATE,
    "P10": PerilStatus.NEEDS_USER_INPUT,
    "P11": PerilStatus.NEEDS_USER_INPUT,
    "P14": PerilStatus.INDETERMINATE,
}


def test_fixture_contains_no_pii():
    raw = (ROOT / "tests/fixtures/nice_06088.json").read_text(encoding="utf-8")
    for forbidden in ("l_denomination_proprietaire", "l_siren", "SCI ", "HABITAT 06"):
        assert forbidden not in raw, forbidden


def test_pii_never_reaches_output(nice, rules):
    r = assess(nice, {}, rules)
    blob = json.dumps(r, ensure_ascii=False)
    assert "siren" not in blob.lower()
    assert "proprietaire" not in blob.lower()


def test_expected_statuses_without_answers(nice, rules):
    r = assess(nice, {}, rules)
    got = {pid: p["status"] for pid, p in r["perils"].items()}
    assert got == EXPECTED_NO_ANSWERS


def test_p02_uses_published_clay_class_and_not_brgm_algorithm(nice, rules):
    r = assess(nice, {}, rules)["perils"]["P02"]
    f = r["frequency"]
    assert "hazard.clay.exposure_class" in f["used_variables"]
    detail = next(d for d in f["detail"] if d["key"] == "hazard.clay.exposure_class")
    assert detail["value"] == "Moyen"
    assert detail["index"] == pytest.approx(0.66)
    # Aucune variable lithologique / mineralogique / geotechnique ne doit apparaitre.
    for u in f["used_variables"]:
        assert not any(t in u for t in ("litho", "mineral", "geotech", "plasticite"))


def test_p03_frequency_from_official_seismic_zone(nice, rules):
    r = assess(nice, {}, rules)["perils"]["P03"]
    assert r["status"] == PerilStatus.CALCULATED
    detail = next(d for d in r["frequency"]["detail"] if d["key"] == "hazard.seismic.zone")
    assert detail["value"] == "4"
    assert detail["index"] == pytest.approx(0.75)
    assert r["frequency"]["score"] == 75


def test_p03_vulnerability_uses_precise_structure_field(nice, rules):
    """`materiaux_structure_mur_exterieur` doit primer sur `mat_mur_txt=INDETERMINE`."""
    r = assess(nice, {}, rules)["perils"]["P03"]
    detail = next(d for d in r["vulnerability"]["detail"]
                  if d["key"] == "building.structure.wall_material")
    assert detail["value"] == "murs en beton banche"


def test_p01_indeterminate_because_azi_source_error(nice, rules):
    r = assess(nice, {}, rules)["perils"]["P01"]
    assert r["status"] == PerilStatus.INDETERMINATE
    assert r["risk"] is None
    m = next(m for m in r["frequency"]["missing_variables"]
             if m["key"] == "hazard.flood.zone")
    assert m["status"] == "SOURCE_ERROR"


def test_p04_is_decomposed_and_never_aggregated(nice, rules):
    r = assess(nice, {}, rules)
    subs = [p for p in r["perils"] if p.startswith("P04")]
    assert set(subs) == {"P04-CAV", "P04-GLI", "P04-BLO", "P04-TAS"}
    assert "P04" not in r["perils"]


def test_p04_cav_zero_results_is_not_zero_risk(nice, rules):
    """cavites.results = 0 ne doit pas devenir un indice d'alea nul."""
    r = assess(nice, {}, rules)["perils"]["P04-CAV"]
    assert r["status"] == PerilStatus.INDETERMINATE
    m = next(m for m in r["frequency"]["missing_variables"]
             if m["key"] == "hazard.landslide.cavities_count")
    assert m["status"] == "NO_FEATURE_FOUND"
    assert "absence d'objet" in m["reason"]


def test_p05_p09_indeterminate_for_missing_climate(nice, rules):
    r = assess(nice, {}, rules)
    for pid, key in (("P05", "climate.wind_speed_max_stat"),
                     ("P09", "site.distance_to_forest")):
        p = r["perils"][pid]
        assert p["status"] == PerilStatus.INDETERMINATE
        assert any(m["key"] == key for m in p["frequency"]["missing_variables"])


def test_p06_p07_p10_never_produce_f_or_r(nice, answers_apartment, rules):
    for answers in ({}, answers_apartment):
        r = assess(nice, answers, rules)
        for pid in ("P06", "P07", "P10"):
            p = r["perils"][pid]
            assert p["frequency"] is None, pid
            assert p["risk"] is None, pid
            assert p["status"] in (PerilStatus.VULNERABILITY_ONLY,
                                   PerilStatus.NEEDS_USER_INPUT), pid


def test_vulnerability_only_carries_mandatory_label(nice, answers_apartment, rules):
    r = assess(nice, answers_apartment, rules)
    for pid in ("P06", "P07", "P10"):
        p = r["perils"][pid]
        assert p["status"] == PerilStatus.VULNERABILITY_ONLY
        assert p["vulnerability"]["label"] == (
            "Sensibilite du batiment hors exposition — ne constitue pas un score de risque")


def test_typology_detected_as_collective(nice, rules):
    r = assess(nice, {}, rules)
    t = r["building_typology"]
    assert t["kind"] == "collective"
    assert any("nb_niveau=17" in s for s in t["signals"])
    assert r["perils"]["P02"]["warnings"], "un caveat de typologie est attendu sur P02"


def test_entity_match_is_group_level(nice, rules):
    r = assess(nice, {}, rules)
    em = r["entity_match"]
    assert em["level"] == "building_group"
    assert em["n_addresses_in_group"] == 11
    assert "differente de l'adresse principale" in em["reason"]
    assert em["parcel_ids"] == ["06088000OH0409"]


def test_catnat_pagination_incompleteness_is_reported(nice, rules):
    r = assess(nice, {}, rules)
    cat = r["catnat_context"]
    assert cat["records_announced"] == 83
    assert cat["records_present"] == 4
    assert cat["pagination_complete"] is False
    assert "Pagination incomplete" in cat["warning"]


def test_answers_unlock_expected_perils(nice, answers_apartment, rules):
    r = assess(nice, answers_apartment, rules)
    assert r["perils"]["P08"]["status"] == PerilStatus.CALCULATED
    assert r["perils"]["P11"]["status"] == PerilStatus.CALCULATED
    for pid in ("P06", "P07", "P10"):
        assert r["perils"][pid]["status"] == PerilStatus.VULNERABILITY_ONLY


def test_user_unknown_is_not_treated_as_unfavourable(nice, rules):
    """Repondre 'Je ne sais pas' ne doit jamais valoir le pire cas."""
    unknown = {"building.seismic.soft_storey": {"value": None, "basis": "inconnu"}}
    worst = {"building.seismic.soft_storey": {"value": True, "basis": "observe"}}
    v_unknown = assess(nice, unknown, rules)["perils"]["P03"]["vulnerability"]["score_raw"]
    v_worst = assess(nice, worst, rules)["perils"]["P03"]["vulnerability"]["score_raw"]
    assert v_unknown < v_worst


def test_questionnaire_is_dynamic_and_prioritised(nice, rules):
    r = assess(nice, {}, rules)
    q = build_questionnaire(r, {})
    assert q["n_questions"] > 0
    keys = [qq["key"] for s in q["sections"] for qq in s["questions"]]
    # En collectif, ni fondations ni toiture ne sont demandees.
    assert not any("foundation" in k for k in keys)
    assert not any(".roof." in k for k in keys)
    # Les questions debloquantes passent en priorite 1.
    p1 = [qq for s in q["sections"] for qq in s["questions"] if qq["priority"] == 1]
    assert p1 and all(qq["unlocks_perils"] for qq in p1)


def test_answered_questions_are_not_asked_again(nice, answers_apartment, rules):
    r = assess(nice, answers_apartment, rules)
    q = build_questionnaire(r, answers_apartment)
    keys = {qq["key"] for s in q["sections"] for qq in s["questions"]}
    assert not (keys & set(answers_apartment)), "question deja repondue reposee"


def test_confidence_is_independent_of_risk(nice, answers_apartment, rules):
    r = assess(nice, answers_apartment, rules)
    for pid, p in r["perils"].items():
        c = p["confidence"]
        assert c["independent_of_risk"] is True
        assert 0 <= c["score"] <= 100, pid


def test_confidence_flags_group_scope_and_provisional_weights(nice, rules):
    r = assess(nice, {}, rules)["perils"]["P03"]
    reasons = " | ".join(r["confidence"]["reasons"])
    assert "GROUPE de batiments" in reasons
    assert "provisoire" in reasons
