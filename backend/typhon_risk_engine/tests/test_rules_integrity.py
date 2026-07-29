"""Integrite du jeu de regles : poids, transformations, metadonnees."""
import pytest

from risk_engine.rules_loader import REQUIRED_VAR_FIELDS, RulesError, load_rules
from risk_engine.transforms import ALLOWED_TRANSFORMS

PERILS_IN_SCOPE = {"P01", "P02", "P03", "P04-CAV", "P04-GLI", "P04-BLO", "P04-TAS",
                   "P05", "P06", "P07", "P08", "P09", "P10", "P11", "P14"}
OUT_OF_SCOPE = {"P12", "P13", "P18"}


def test_scope_exact(rules):
    assert set(rules["perils"]) == PERILS_IN_SCOPE
    assert not (set(rules["perils"]) & OUT_OF_SCOPE)


def test_weights_sum_to_one(rules):
    for pid, spec in rules["perils"].items():
        for block_name in ("frequency", "vulnerability"):
            block = spec.get(block_name)
            if not block:
                continue
            scored = [v for v in block["variables"] if v["role"] in ("F", "V")]
            if not scored:
                continue
            total = sum(v["weight"] for v in scored)
            assert abs(total - 1.0) < 1e-9, f"{pid}/{block_name} = {total}"


def test_exactly_one_dominant_per_block(rules):
    for pid, spec in rules["perils"].items():
        for block_name in ("frequency", "vulnerability"):
            block = spec.get(block_name)
            if not block:
                continue
            scored = [v for v in block["variables"] if v["role"] in ("F", "V")]
            if not scored:
                continue
            n = sum(1 for v in scored if v.get("dominant"))
            assert n == 1, f"{pid}/{block_name} a {n} variable(s) dominante(s)"


def test_required_metadata_present(rules):
    for pid, spec in rules["perils"].items():
        for block_name in ("frequency", "vulnerability"):
            for v in (spec.get(block_name) or {}).get("variables", []):
                for f in REQUIRED_VAR_FIELDS:
                    assert f in v, f"{pid}/{v.get('key')} : champ {f} manquant"
                assert v["references"], f"{pid}/{v['key']} sans reference"
                assert v["transform"]["type"] in ALLOWED_TRANSFORMS


def test_no_hazard_variables_when_hazard_unavailable(rules):
    for pid, spec in rules["perils"].items():
        if not spec["hazard_available"]:
            assert not (spec.get("frequency") or {}).get("variables"), pid


def test_protections_cannot_increase_v(rules):
    for pid, spec in rules["perils"].items():
        for v in (spec.get("vulnerability") or {}).get("variables", []):
            if v["role"] == "protection":
                assert 0.0 <= v["max_reduction"] <= 1.0, f"{pid}/{v['key']}"


def test_rules_digest_is_stable(rules):
    again = load_rules()
    assert rules["rules_digest"] == again["rules_digest"]


def test_loader_rejects_bad_weights(tmp_path):
    (tmp_path / "_common.yaml").write_text(
        "rules_version: t\ncombination: {exponent_f: 0.5, exponent_v: 0.5, v_min: 10,"
        " protection_cap: 0.5, formula_label: x}\n"
        "publication: {max_missing_weight: 0.5, rank5_confidence_cap: 40}\n"
        "confidence: {components: {a: 1.0}}\nrisk_classes: []\n", encoding="utf-8")
    (tmp_path / "PX.yaml").write_text(
        "peril_id: PX\nhazard_available: true\nfrequency:\n  variables:\n"
        "  - {key: k, raw_paths: [x], role: F, dominant: true, weight: 0.5,"
        " transform: {type: boolean}, direction: increasing,"
        " physical_mechanism: m, min_source_rank: 4, allowed_scopes: [building],"
        " allowed_time_horizons: [current], on_missing: x, on_conflict: x,"
        " evidence_level: low, references: [r], calibration_status: provisional_modeling_weight}\n",
        encoding="utf-8")
    with pytest.raises(RulesError, match="somme des poids"):
        load_rules(tmp_path)
