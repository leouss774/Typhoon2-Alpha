"""L'analyse de sensibilite est un DIAGNOSTIC : elle doit s'executer et rapporter,
jamais servir a ajuster les poids."""
import json
from pathlib import Path

import pytest

from tools.sensitivity import perturb, run

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def high():
    c = json.loads((ROOT / "tests/fixtures/synthetic_high.json").read_text(encoding="utf-8"))
    a = json.loads((ROOT / "tests/fixtures/synthetic_high_answers.json").read_text(encoding="utf-8"))
    return c, a


def test_perturbation_keeps_weights_normalised(rules):
    p = perturb(rules, "P02", "frequency", "hazard.clay.exposure_class", 0.10)
    scored = [v for v in p["perils"]["P02"]["frequency"]["variables"] if v["role"] == "F"]
    assert sum(v["weight"] for v in scored) == pytest.approx(1.0)


def test_sensitivity_runs_and_reports(high):
    rep = run(*high, delta=0.10)
    assert rep["n_provisional_weights_tested"] > 0
    assert rep["n_perturbations"] == 2 * rep["n_provisional_weights_tested"]
    assert "critical_weights" in rep
    assert "Diagnostic uniquement" in rep["note"]


def test_only_provisional_weights_are_perturbed(high, rules):
    """Les seuils publies (zonage sismique, classe argile) ne sont pas perturbes."""
    rep = run(*high, delta=0.10)
    tested = {(d["peril"], d["key"]) for d in rep["details"]}
    assert ("P03", "hazard.seismic.zone") not in tested
    assert ("P02", "hazard.clay.exposure_class") not in tested


def test_critical_weights_are_reported_not_silenced(high):
    """Le rapport doit exposer les poids critiques, meme s'il y en a."""
    rep = run(*high, delta=0.10)
    for c in rep["details"]:
        assert c["class_changed"] or c["status_changed"]
        assert c["peril"] and c["key"]
