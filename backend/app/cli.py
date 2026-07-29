"""
Script de test de l'orchestrateur (collector_agent) en ligne de commande.

Trois modes d'utilisation :

  1. Une seule adresse en argument :
       python -m app.cli "10 Promenade des Anglais, 06000 Nice"

  2. Mode interactif (aucune adresse en argument) : boucle qui demande une
     adresse a la fois, affiche/sauvegarde le resultat, et recommence -
     pratique pour tester plusieurs adresses de suite sans relancer le
     process a chaque fois (le cache Copernicus reste chaud entre deux
     adresses) :
       python -m app.cli
       > Adresse a diagnostiquer (ou 'quit') : 1 place Massena, 06000 Nice
       ...
       > Adresse a diagnostiquer (ou 'quit') : quit

  3. Mode batch : un fichier texte avec une adresse par ligne, traitees
     sequentiellement :
       python -m app.cli --batch adresses_paca.txt

Par defaut, le script previent (sans bloquer definitivement) si l'adresse
est hors region PACA (04, 05, 06, 13, 83, 84), perimetre du sprint MVP
(voir docs/ROADMAP_MVP_PACA.md) ; --force supprime cet avertissement.

Aucune donnee simulee : toute information affichee provient d'un appel
reel a une API (BDNB, Georisques, IGN, Open-Meteo, Copernicus) ou d'un
fichier de lookup local reellement telecharge (DVF). Une source
indisponible apparait comme "null" + une erreur explicite, jamais comme
une valeur inventee.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.agents.collector_agent import collect
from app.core.paca import PACA_DEPARTMENTS


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Teste l'orchestrateur de collecte Typhoon sur une ou plusieurs adresses.")
    parser.add_argument("adresse", nargs="?", help="Adresse a diagnostiquer (omettre pour le mode interactif)")
    parser.add_argument("--out", help="Chemin du fichier JSON de sortie (mode adresse unique uniquement)")
    parser.add_argument("--batch", help="Fichier texte avec une adresse par ligne, traitees a la suite")
    parser.add_argument("--force", action="store_true", help="Ne pas avertir si l'adresse est hors region PACA")
    parser.add_argument("--no-copernicus", action="store_true", help="Desactiver Copernicus CDS dans la collecte")
    return parser.parse_args()


def _out_path(citycode: str, override: str | None = None) -> Path:
    return Path(override) if override else Path("out") / f"{citycode}.json"


async def _run_one(address: str, out_override: str | None, force: bool, enable_copernicus: bool = True) -> dict:
    print(f"\nCollecte en cours pour : {address}", file=sys.stderr)
    building_data = await collect(address, enable_copernicus=enable_copernicus)

    departement = building_data["departement"]
    if departement not in PACA_DEPARTMENTS and not force:
        print(
            f"  -> departement {departement} hors PACA (perimetre du sprint MVP). "
            "Resultat quand meme sauvegarde ; utilisez --force pour supprimer cet avertissement.",
            file=sys.stderr,
        )

    output_json = json.dumps(building_data, indent=2, ensure_ascii=False, default=str)
    out_path = _out_path(building_data["adresse"]["citycode"], out_override)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output_json, encoding="utf-8")

    nb_erreurs = len(building_data["erreurs"])
    print(f"  -> JSON sauvegarde dans {out_path} ({nb_erreurs} source(s) en erreur)", file=sys.stderr)
    for erreur in building_data["erreurs"]:
        print(f"     - {erreur['source']}: {erreur['erreur']}", file=sys.stderr)

    return building_data


async def _interactive_loop(force: bool, enable_copernicus: bool = True) -> None:
    print(
        "Mode interactif : tapez une adresse puis Entree pour lancer un diagnostic. "
        "Tapez 'quit' pour quitter.\n",
        file=sys.stderr,
    )
    loop = asyncio.get_event_loop()
    while True:
        address = await loop.run_in_executor(None, input, "Adresse a diagnostiquer (ou 'quit') : ")
        address = address.strip()
        if address.lower() in {"quit", "exit", ""}:
            break
        try:
            building_data = await _run_one(address, None, force, enable_copernicus=enable_copernicus)
            print(json.dumps(building_data, indent=2, ensure_ascii=False, default=str))
        except Exception as exc:
            print(f"Echec du diagnostic pour cette adresse : {exc}", file=sys.stderr)


async def _batch_run(batch_file: str, force: bool, enable_copernicus: bool = True) -> int:
    addresses = [line.strip() for line in Path(batch_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"{len(addresses)} adresse(s) a traiter depuis {batch_file}", file=sys.stderr)

    nb_echecs = 0
    for address in addresses:
        try:
            await _run_one(address, None, force, enable_copernicus=enable_copernicus)
        except Exception as exc:
            nb_echecs += 1
            print(f"Echec du diagnostic pour {address!r} : {exc}", file=sys.stderr)

    print(f"\nTermine : {len(addresses) - nb_echecs}/{len(addresses)} adresse(s) traitees avec succes.", file=sys.stderr)
    return 1 if nb_echecs else 0


async def _main() -> int:
    args = _parse_args()
    copernicus_enabled = not args.no_copernicus

    if args.batch:
        return await _batch_run(args.batch, args.force, enable_copernicus=copernicus_enabled)

    if args.adresse is None:
        await _interactive_loop(args.force, enable_copernicus=copernicus_enabled)
        return 0

    building_data = await _run_one(args.adresse, args.out, args.force, enable_copernicus=copernicus_enabled)
    print(json.dumps(building_data, indent=2, ensure_ascii=False, default=str))
    return 0


def main() -> None:
    sys.exit(asyncio.run(_main()))


if __name__ == "__main__":
    main()
