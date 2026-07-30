"""Regles de calcul : indetermination, monotonie, protections, bornes."""
import copy

import pytest

from risk_engine.engine import PerilStatus, _combine, assess


def _mk_answers(**kw):
    return {k: {"value": v, "basis": "observe"} for k, v in kw.items()}


# --- Indetermination ---------------------------------------------------------------


def test_dominant_missing_gives_indeterminate_even_under_50pct(nice, rules):
    """P02 : dominante presente -> F calculable. On la retire -> INDETERMINE,
    alors que seuls 70 % du poids manquent... et surtout la regle 16 s'applique."""
    r = assess(nice, {}, rules)
    assert r["perils"]["P02"]["frequency"]["determinate"] is True

    stripped = copy.deepcopy(nice)
    stripped["bdnb"]["batiment"].pop("alea_argile")
    r2 = assess(stripped, {}, rules)
    f = r2["perils"]["P02"]["frequency"]
    assert f["determinate"] is False
    assert "dominante" in f["indeterminate_reason"]
    assert r2["perils"]["P02"]["risk"] is None


def test_more_than_half_weight_missing_gives_indeterminate(nice, rules):
    """P05 V : seule la dominante repondue -> 65 % manquant -> INDETERMINE."""
    a = _mk_answers(**{"questionnaire.building.roof.material": "bac_acier"})
    r = assess(nice, a, rules)
    v = r["perils"]["P05"]["vulnerability"]
    assert v["determinate"] is False
    assert "poids theorique manquant" in v["indeterminate_reason"]


def test_indeterminate_never_hides_a_score(nice, rules):
    r = assess(nice, {}, rules)
    for pid, p in r["perils"].items():
        if p["status"] == PerilStatus.INDETERMINATE:
            assert p["risk"] is None, pid
            for blk in ("frequency", "vulnerability"):
                b = p.get(blk)
                if b and not b["determinate"]:
                    assert b["score"] is None, f"{pid}/{blk}"


def test_renormalisation_only_when_dominant_present(nice, rules):
    """P02 F : dominante presente, 30 % manquant -> renormalisation autorisee.
    L'indice 0.66 de la classe Moyen doit se retrouver tel quel apres renormalisation."""
    r = assess(nice, {}, rules)
    f = r["perils"]["P02"]["frequency"]
    assert f["coverage"] == pytest.approx(0.70)
    assert f["score"] == 66


# --- Exclusions ------------------------------------------------------------------------


def test_default_values_excluded(nice, rules):
    """Une valeur par defaut injectee ne doit jamais alimenter un score."""
    from risk_engine.canonical import CanonicalVariable, Status
    from risk_engine.normalizer import normalize
    bag, _ = normalize(nice, {})
    bag.add(CanonicalVariable(key="hazard.hail.default", value=1,
                              status=Status.AVAILABLE, is_default=True))
    assert bag.get("hazard.hail.default").status is Status.DEFAULT_VALUE
    assert not bag.get("hazard.hail.default").usable


def test_catnat_and_commune_booleans_have_zero_weight_in_f(nice, rules):
    r = assess(nice, {}, rules)
    assert r["catnat_context"]["weight_in_F"] == 0.0
    assert r["commune_context"]["weight_in_F"] == 0.0
    for pid, p in r["perils"].items():
        assert p["current_context"]["weight_in_F"] == 0.0, pid
        used = (p.get("frequency") or {}).get("used_variables", []) or []
        assert not any("catnat" in u.lower() or "commune_context" in u.lower()
                       for u in used), pid


def test_current_and_prospective_are_separated(nice, rules):
    r = assess(nice, {}, rules)
    assert r["prospective_context"]["available"] is False
    for pid, p in r["perils"].items():
        assert p["prospective_context"] in ({}, None) or "jamais" in str(
            p["prospective_context"])


def test_source_error_blocks_but_is_labelled(nice, rules):
    r = assess(nice, {}, rules)
    f = r["perils"]["P01"]["frequency"]
    reasons = [m["reason"] for m in f["missing_variables"]
               if m["key"] == "hazard.flood.zone"]
    assert reasons and "SOURCE_ERROR" in reasons[0]
    assert "absence" in reasons[0] or "pas une absence" in reasons[0]


# --- Combinaison, monotonie, bornes -----------------------------------------------------


def test_f_zero_gives_r_zero(rules):
    assert _combine(0.0, 90.0, rules["common"]) == 0.0


def test_r_monotone_in_f_and_v(rules):
    c = rules["common"]
    prev = -1.0
    for f in range(0, 101, 5):
        r = _combine(float(f), 50.0, c)
        assert r >= prev - 1e-9
        prev = r
    prev = -1.0
    for v in range(0, 101, 5):
        r = _combine(50.0, float(v), c)
        assert r >= prev - 1e-9
        prev = r


def test_r_bounded_0_100(rules):
    c = rules["common"]
    assert _combine(100.0, 100.0, c) == pytest.approx(100.0)
    assert 0.0 <= _combine(37.0, 61.0, c) <= 100.0


def test_protection_can_only_decrease_v(nice, rules):
    base = assess(nice, _mk_answers(**{
        "questionnaire.building.plumbing.material": "cuivre",
        "questionnaire.building.plumbing.unheated_pipes": "nombreuses",
        "questionnaire.building.plumbing.joints_state": "degrade",
        "questionnaire.building.flat_roof_or_walkin_shower": True,
        "building.basement": "sous_sol_total",
    }), rules)
    protected = assess(nice, _mk_answers(**{
        "questionnaire.building.plumbing.material": "cuivre",
        "questionnaire.building.plumbing.unheated_pipes": "nombreuses",
        "questionnaire.building.plumbing.joints_state": "degrade",
        "questionnaire.building.flat_roof_or_walkin_shower": True,
        "building.basement": "sous_sol_total",
        "questionnaire.building.plumbing.leak_detector": True,
        "questionnaire.building.plumbing.auto_shutoff": True,
        "questionnaire.building.plumbing.insulation": True,
    }), rules)
    v0 = base["perils"]["P11"]["vulnerability"]["score_raw"]
    v1 = protected["perils"]["P11"]["vulnerability"]["score_raw"]
    assert v1 <= v0
    assert protected["perils"]["P11"]["vulnerability"]["protection_reduction"] > 0


def test_protection_cap_is_50pct(nice, rules):
    """Trois protections cumulees (0.15, 0.20, 0.15) plafonnent a 0.50."""
    r = assess(nice, _mk_answers(**{
        "questionnaire.building.plumbing.material": "plomb",
        "questionnaire.building.plumbing.unheated_pipes": "nombreuses",
        "questionnaire.building.plumbing.joints_state": "degrade",
        "questionnaire.building.flat_roof_or_walkin_shower": True,
        "building.basement": "sous_sol_total",
        "questionnaire.building.plumbing.leak_detector": True,
        "questionnaire.building.plumbing.auto_shutoff": True,
        "questionnaire.building.plumbing.insulation": True,
    }), rules)
    red = r["perils"]["P11"]["vulnerability"]["protection_reduction"]
    assert red <= rules["common"]["combination"]["protection_cap"] + 1e-9


def test_v_min_floor(nice, answers_apartment, rules):
    v_min = rules["common"]["combination"]["v_min"]
    r = assess(nice, answers_apartment, rules)
    for pid, p in r["perils"].items():
        v = p.get("vulnerability")
        if v and v["determinate"]:
            assert v["score_raw"] >= v_min - 1e-9, pid


# --- Reproductibilite -------------------------------------------------------------------


def test_bit_for_bit_reproducible(nice, answers_apartment, rules):
    import json
    a = json.dumps(assess(nice, answers_apartment, rules), sort_keys=True)
    b = json.dumps(assess(nice, answers_apartment, rules), sort_keys=True)
    assert a == b


def test_no_global_score_and_no_money(nice, answers_apartment, rules):
    """Aucun agregat multi-perils, aucune sortie monetaire.

    La recherche est faite sur des motifs delimites : `Eurocode` est une norme
    citee en reference, ce n'est pas une valeur en euros.
    """
    import json
    import re
    r = assess(nice, answers_apartment, rules)
    assert r["global_score"] is None
    assert r["monetary_output"] is None

    # Aucune cle de sortie ne porte un montant.
    def walk_keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield k
                yield from walk_keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk_keys(v)

    money_keys = re.compile(
        r"(aal|montant|cout|prix|euro(?!code)|valeur_(reconstruction|assuree)|perte)",
        re.IGNORECASE)
    offending = [k for k in walk_keys(r) if money_keys.search(k)]
    assert not offending, offending

    blob = json.dumps(r, ensure_ascii=False)
    assert "\u20ac" not in blob                      # symbole euro
    assert not re.search(r"\bAAL\b", blob, re.IGNORECASE)
    assert not re.search(r"\d\s?(EUR|euros)\b", blob, re.IGNORECASE)

    # Aucun peril ne porte de score agrege avec un autre.
    scores = [p.get("risk") for p in r["perils"].values() if p.get("risk")]
    assert all(set(s) <= {"score", "score_raw", "class", "formula",
                          "calibration_status"} for s in scores)
