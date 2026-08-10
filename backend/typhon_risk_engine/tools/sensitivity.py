"""
Analyse de sensibilite des ponderations provisoires.

Chaque poids est perturbe de +/- delta, les poids du bloc sont renormalises a 1,
et l'on observe si un bien change de CLASSE DE LECTURE.

Ceci est un DIAGNOSTIC, pas une calibration : les poids ne doivent jamais etre
ajustes pour faire passer le test.
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from risk_engine.engine import assess          # noqa: E402
from risk_engine.rules_loader import load_rules  # noqa: E402


def perturb(rules: dict, pid: str, block: str, key: str, delta: float) -> dict:
    out = copy.deepcopy(rules)
    variables = out["perils"][pid][block]["variables"]
    role = "F" if block == "frequency" else "V"
    scored = [v for v in variables if v["role"] == role]
    for v in scored:
        if v["key"] == key:
            v["weight"] = max(0.0, min(1.0, v["weight"] + delta))
    total = sum(v["weight"] for v in scored)
    if total <= 0:
        return out
    for v in scored:
        v["weight"] = v["weight"] / total
    return out


def run(collector: dict, answers: dict, delta: float = 0.10) -> dict:
    rules = load_rules()
    base = assess(collector, answers, rules)
    findings, critical = [], []

    for pid, spec in sorted(rules["perils"].items()):
        for block in ("frequency", "vulnerability"):
            blk = spec.get(block)
            if not blk:
                continue
            role = "F" if block == "frequency" else "V"
            scored = [v for v in blk["variables"] if v["role"] == role]
            for v in scored:
                if v["calibration_status"] != "provisional_modeling_weight":
                    continue
                for d in (+delta, -delta):
                    r2 = assess(collector, answers, perturb(rules, pid, block, v["key"], d))
                    b, p = base["perils"][pid], r2["perils"][pid]
                    rec = {
                        "peril": pid, "block": block, "key": v["key"],
                        "delta": d, "base_weight": v["weight"],
                        "status_before": b["status"], "status_after": p["status"],
                        "risk_before": (b.get("risk") or {}).get("score"),
                        "risk_after": (p.get("risk") or {}).get("score"),
                        "class_before": (b.get("risk") or {}).get("class"),
                        "class_after": (p.get("risk") or {}).get("class"),
                    }
                    rec["class_changed"] = (
                        rec["class_before"] is not None
                        and rec["class_before"] != rec["class_after"])
                    rec["status_changed"] = rec["status_before"] != rec["status_after"]
                    findings.append(rec)
                    if rec["class_changed"] or rec["status_changed"]:
                        critical.append(rec)

    tested = {(f["peril"], f["block"], f["key"]) for f in findings}
    return {
        "delta": delta,
        "n_provisional_weights_tested": len(tested),
        "n_perturbations": len(findings),
        "n_class_or_status_changes": len(critical),
        "critical_weights": sorted(
            {(c["peril"], c["block"], c["key"]) for c in critical}),
        "details": critical,
        "note": ("Diagnostic uniquement. Un poids critique doit etre justifie par une "
                 "source ou la variable retiree — jamais ajuste pour faire passer le test."),
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("collector_json", type=Path)
    ap.add_argument("--answers", type=Path, default=None)
    ap.add_argument("--delta", type=float, default=0.10)
    ap.add_argument("--out", type=Path, default=None)
    a = ap.parse_args(argv)

    collector = json.loads(a.collector_json.read_text(encoding="utf-8"))
    answers = json.loads(a.answers.read_text(encoding="utf-8")) if a.answers else {}
    rep = run(collector, answers, a.delta)
    payload = json.dumps(rep, ensure_ascii=False, indent=2)
    if a.out:
        a.out.write_text(payload, encoding="utf-8")
    print(f"poids provisoires testes : {rep['n_provisional_weights_tested']}")
    print(f"perturbations            : {rep['n_perturbations']} (delta = +/-{rep['delta']})")
    print(f"changements de classe/statut : {rep['n_class_or_status_changes']}")
    for k in rep["critical_weights"]:
        print("   POIDS CRITIQUE :", " / ".join(k))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
