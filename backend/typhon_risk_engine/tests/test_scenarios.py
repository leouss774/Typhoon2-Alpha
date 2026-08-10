"""Cas faible / moyen / eleve / incomplet / contradictoire / fortement protege.

Les fixtures `synthetic_*` sont des cas de test CONSTRUITS, pas des donnees
reelles ; elles portent le drapeau `_synthetic`.
"""
import json
from pathlib import Path

import pytest

from risk_engine.engine import PerilStatus, assess

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "tests/fixtures"


def _load(name):
    c = json.loads((FX / f"{name}.json").read_text(encoding="utf-8"))
    a = json.loads((FX / f"{name}_answers.json").read_text(encoding="utf-8"))
    return c, a


@pytest.fixture(scope="module")
def scenarios(request):
    return {n: _load(n) for n in
            ("synthetic_low", "synthetic_medium", "synthetic_high",
             "synthetic_incomplete", "synthetic_conflict", "synthetic_protected")}


def test_fixtures_are_flagged_synthetic(scenarios):
    for name, (c, _) in scenarios.items():
        assert c.get("_synthetic") is True, name


def test_low_medium_high_are_ordered(scenarios, rules):
    """Le classement doit etre monotone entre les trois scenarios."""
    res = {n: assess(*scenarios[n], rules) for n in
           ("synthetic_low", "synthetic_medium", "synthetic_high")}
    for pid in ("P02", "P08", "P11"):
        lo, me, hi = (res[n]["perils"][pid]["risk"] for n in
                      ("synthetic_low", "synthetic_medium", "synthetic_high"))
        assert lo["score"] <= me["score"] <= hi["score"], pid


def test_protection_strictly_reduces_risk(scenarios, rules):
    """Meme alea, memes facteurs, protections en plus : R ne peut que baisser."""
    hi = assess(*scenarios["synthetic_high"], rules)
    pr = assess(*scenarios["synthetic_protected"], rules)
    for pid in ("P03", "P08", "P11"):
        r_hi = hi["perils"][pid]["risk"]["score"]
        r_pr = pr["perils"][pid]["risk"]["score"]
        assert r_pr <= r_hi, f"{pid}: protege {r_pr} > non protege {r_hi}"
    assert pr["perils"]["P11"]["vulnerability"]["protection_reduction"] > 0


def test_incomplete_case_never_invents_a_score(scenarios, rules):
    r = assess(*scenarios["synthetic_incomplete"], rules)
    for pid, p in r["perils"].items():
        if p["status"] in (PerilStatus.INDETERMINATE, PerilStatus.NEEDS_USER_INPUT):
            assert p["risk"] is None, pid
    # Une absence de reponse doit produire des questions, pas un risque par defaut.
    assert any(p["required_user_questions"] for p in r["perils"].values())


def test_incomplete_lowers_confidence_not_risk(scenarios, rules):
    full = assess(*scenarios["synthetic_medium"], rules)
    empty_collector, _ = scenarios["synthetic_incomplete"]
    empty = assess(empty_collector, {}, rules)
    # P03 est calculable dans les deux cas : la confiance doit baisser sans que
    # le risque augmente mecaniquement.
    c_full = full["perils"]["P03"]["confidence"]["score"]
    c_empty = empty["perils"]["P03"]["confidence"]["score"]
    assert c_empty <= c_full


def test_conflict_is_detected_and_hierarchy_applied(scenarios, rules):
    """L'utilisateur declare beton arme et 2015 ; BDNB dit moellons et 1935.
    Un document (rang 1) prime sur BDNB (rang 4), mais le conflit est signale."""
    r = assess(*scenarios["synthetic_conflict"], rules)
    p3 = r["perils"]["P03"]
    detail = next(d for d in p3["vulnerability"]["detail"]
                  if d["key"] == "building.structure.wall_material")
    assert detail["value"] == "beton arme"
    assert detail["source_rank"] == 1
    reasons = " | ".join(p3["confidence"]["reasons"])
    assert "conflit" in reasons.lower()


def test_conflict_reduces_coherence_component(scenarios, rules):
    conflict = assess(*scenarios["synthetic_conflict"], rules)
    clean = assess(*scenarios["synthetic_medium"], rules)
    assert (conflict["perils"]["P03"]["confidence"]["components"]["coherence"]
            < clean["perils"]["P03"]["confidence"]["components"]["coherence"])


def test_house_vs_apartment_typology(scenarios, nice, rules):
    house = assess(*scenarios["synthetic_medium"], rules)
    flat = assess(nice, {}, rules)
    assert house["building_typology"]["kind"] == "individual_house"
    assert flat["building_typology"]["kind"] == "collective"
    # Le caveat de typologie n'apparait que pour le collectif.
    assert not any("collectif" in w for w in house["perils"]["P02"]["warnings"])
    assert any("collectif" in w for w in flat["perils"]["P02"]["warnings"])


def test_building_group_scope_is_distinguished(nice, scenarios, rules):
    flat = assess(nice, {}, rules)
    assert flat["entity_match"]["level"] == "building_group"
    d = next(x for x in flat["perils"]["P03"]["vulnerability"]["detail"]
             if x["key"] == "building.structure.wall_material")
    assert d["scope"] == "building_group"
    house = assess(*scenarios["synthetic_medium"], rules)
    dh = next(x for x in house["perils"]["P03"]["vulnerability"]["detail"]
              if x["key"] == "building.structure.wall_material")
    # Observation directe de l'occupant (rang 2) : meilleure que BDNB (rang 4),
    # et rattachee au logement, pas au groupe de batiments.
    assert dh["source_rank"] == 2
    assert dh["scope"] == "dwelling"


def test_no_variable_counted_twice_within_a_peril(rules):
    """Une meme cle ne peut pas peser dans F et dans V du meme peril."""
    for pid, spec in rules["perils"].items():
        f_keys = {v["key"] for v in (spec.get("frequency") or {}).get("variables", [])
                  if v["role"] == "F"}
        v_keys = {v["key"] for v in (spec.get("vulnerability") or {}).get("variables", [])
                  if v["role"] == "V"}
        assert not (f_keys & v_keys), f"{pid}: {f_keys & v_keys}"


def test_no_duplicate_keys_within_a_block(rules):
    for pid, spec in rules["perils"].items():
        for block in ("frequency", "vulnerability"):
            keys = [v["key"] for v in (spec.get(block) or {}).get("variables", [])]
            assert len(keys) == len(set(keys)), f"{pid}/{block}"


def test_clay_class_not_double_counted_with_brgm_method(scenarios, rules):
    """P02 consomme la classe publiee ; aucune variable de la methode BRGM
    ayant servi a produire la carte ne doit peser en plus."""
    r = assess(*scenarios["synthetic_medium"], rules)
    used = r["perils"]["P02"]["frequency"]["used_variables"]
    assert "hazard.clay.exposure_class" in used
    banned = ("litho", "mineral", "geotech", "plasticite", "bleu_methylene",
              "retrait_lineaire", "gonflement")
    for u in used:
        assert not any(b in u.lower() for b in banned), u


def test_risk_class_always_resolvable(scenarios, rules):
    for name in scenarios:
        r = assess(*scenarios[name], rules)
        for pid, p in r["perils"].items():
            risk = p.get("risk")
            if risk:
                assert risk["class"] != "indetermine", f"{name}/{pid}"
                assert risk["class"] in {"tres faible", "faible", "modere",
                                         "eleve", "tres eleve"}
