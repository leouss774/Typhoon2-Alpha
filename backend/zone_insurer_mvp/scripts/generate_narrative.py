#!/usr/bin/env python3
"""
Generate narrative and recommendations using Mistral AI from an assessment JSON input.

Usage:
  python scripts/generate_narrative.py report_input.json [--output narrative_out.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add app to path if executed directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.mistral_report import _build_user_prompt, _SYSTEM_PROMPT
from app.services.mistral_client import chat_json


def main():
    parser = argparse.ArgumentParser(description="Generate narrative report via Mistral AI.")
    parser.add_argument("input_json", type=str, help="Path to input assessment report JSON file")
    parser.add_argument("--output", "-o", type=str, help="Path to save output JSON", default=None)
    args = parser.parse_args()

    input_path = Path(args.input_json)
    if not input_path.exists():
        print(f"Error: Input file '{input_path}' not found.", file=sys.stderr)
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        agg_data = json.load(f)

    user_prompt = _build_user_prompt(agg_data)
    print("--- User Prompt ---")
    print(user_prompt)
    print("-------------------")

    print("Requesting response from Mistral AI...")
    try:
        res = chat_json(_SYSTEM_PROMPT, user_prompt)
        print("\n=== Mistral Output ===")
        print(json.dumps(res, indent=2, ensure_ascii=False))

        if args.output:
            out_path = Path(args.output)
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(res, f, indent=2, ensure_ascii=False)
            print(f"\nSaved result to {out_path}")

    except Exception as e:
        print(f"\nError calling Mistral AI: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
