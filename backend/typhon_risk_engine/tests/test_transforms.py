"""Transformation de chaque forme autorisee, et refus des autres."""
import pytest

from risk_engine.transforms import TransformError, apply_transform


def test_categorical_basic():
    spec = {"type": "categorical", "mapping": {"Nul": 0.0, "Moyen": 0.66, "Fort": 1.0},
            "unmapped": None}
    assert apply_transform(spec, "Moyen") == 0.66
    assert apply_transform(spec, "  fort ") == 1.0          # casse et espaces ignores
    with pytest.raises(TransformError):
        apply_transform(spec, "Inexistant")


def test_linear_ramp_interpolates_and_clamps():
    spec = {"type": "linear_ramp", "points": [[0, 0.0], [10, 1.0]]}
    assert apply_transform(spec, 5) == pytest.approx(0.5)
    assert apply_transform(spec, -3) == 0.0
    assert apply_transform(spec, 99) == 1.0


def test_linear_ramp_decreasing():
    spec = {"type": "linear_ramp", "points": [[0, 1.0], [10, 0.0]]}
    assert apply_transform(spec, 2.5) == pytest.approx(0.75)


def test_boolean_forms():
    spec = {"type": "boolean", "true": 1.0, "false": 0.0}
    assert apply_transform(spec, True) == 1.0
    assert apply_transform(spec, "oui") == 1.0
    assert apply_transform(spec, "non") == 0.0
    with pytest.raises(TransformError):
        apply_transform(spec, "peut-etre")


def test_output_always_bounded():
    spec = {"type": "categorical", "mapping": {"x": 5.0}, "unmapped": None}
    assert apply_transform(spec, "x") == 1.0


def test_unknown_transform_rejected():
    with pytest.raises(TransformError):
        apply_transform({"type": "reseau_de_neurones"}, 1)


def test_every_rule_transform_is_exercisable(rules):
    """Chaque transformation declaree doit produire une valeur pour au moins
    une modalite ou un point de sa propre definition."""
    for pid, spec in rules["perils"].items():
        for block in ("frequency", "vulnerability"):
            for v in (spec.get(block) or {}).get("variables", []):
                t = v["transform"]
                if t["type"] == "categorical":
                    sample = next(iter(t["mapping"]))
                elif t["type"] == "linear_ramp":
                    sample = t["points"][0][0]
                else:
                    sample = True
                out = apply_transform(t, sample)
                assert 0.0 <= out <= 1.0, f"{pid}/{v['key']}"
