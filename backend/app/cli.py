"""Script de test de l'orchestrateur (collector_agent) en ligne de commande."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.agents.collector_agent import collect


async def _run_one(address: str) -> dict:
    print(f"\nCollecte en cours pour : {address}", file=sys.stderr)
    building_data = await collect(address)
    print(json.dumps(building_data, indent=2, ensure_ascii=False, default=str))
    return building_data


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Teste l'orchestrateur Typhoon sur une adresse.")
    parser.add_argument("adresse", nargs="?", help="Adresse à diagnostiquer")
    parser.add_argument("--out", help="Chemin du fichier JSON de sortie")
    args = parser.parse_args()

    if not args.adresse:
        parser.print_help()
        return 1

    building_data = await _run_one(args.adresse)
    if args.out:
        Path(args.out).write_text(
            json.dumps(building_data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
