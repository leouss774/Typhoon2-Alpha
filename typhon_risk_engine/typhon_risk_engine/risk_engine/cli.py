"""CLI : evalue un JSON de collector et ecrit le rapport."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import assess
from .questionnaire import build_questionnaire
from .rules_loader import load_rules


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Risk Engine Typhon")
    ap.add_argument("collector_json", type=Path)
    ap.add_argument("--answers", type=Path, default=None)
    ap.add_argument("--rules", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--questionnaire", action="store_true",
                    help="emet aussi le questionnaire dynamique restant")
    args = ap.parse_args(argv)

    collector = json.loads(args.collector_json.read_text(encoding="utf-8"))
    answers = json.loads(args.answers.read_text(encoding="utf-8")) if args.answers else {}
    rules = load_rules(args.rules)

    result = assess(collector, answers, rules)
    if args.questionnaire:
        result["next_questionnaire"] = build_questionnaire(result, answers)

    payload = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=False)
    if args.out:
        args.out.write_text(payload, encoding="utf-8")
        print(f"ecrit : {args.out}")
    else:
        print(payload)

    for pid in sorted(result["perils"]):
        p = result["perils"][pid]
        f = (p.get("frequency") or {}).get("score")
        v = (p.get("vulnerability") or {}).get("score")
        r = (p.get("risk") or {}).get("score")
        c = (p.get("confidence") or {}).get("score")
        print(f"  {pid:9s} {p['status']:20s} F={f!s:>5} V={v!s:>5} R={r!s:>5} conf={c!s:>4}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
