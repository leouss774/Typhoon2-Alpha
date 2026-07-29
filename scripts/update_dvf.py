"""
Script de mise à jour de la base DVF locale.

Usage :
    python scripts/update_dvf.py              # Télécharge et indexe toutes les années
    python scripts/update_dvf.py --years 2025  # Télécharge et indexe 2025 uniquement

Ce script télécharge les fichiers DVF depuis data.gouv.fr (DGFiP),
les parse et les indexe dans une base SQLite locale pour des requêtes rapides.

Les données DVF sont publiées semestriellement (avril + octobre).
Exécutez ce script après chaque publication pour mettre à jour les prix.
"""

import argparse
import logging
import sys
import os

# Ajouter le backend au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_dvf")


def main():
    parser = argparse.ArgumentParser(
        description="Mise à jour de la base DVF locale (DGFiP - data.gouv.fr)"
    )
    parser.add_argument(
        "--years",
        type=int,
        nargs="+",
        help="Années à télécharger/indexer (ex: --years 2025 2024). Défaut : toutes.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Ignorer le téléchargement (réindexer seulement les fichiers déjà téléchargés)",
    )
    parser.add_argument(
        "--info",
        action="store_true",
        help="Afficher les métadonnées de la base existante",
    )
    args = parser.parse_args()

    from backend.services import dvf_service

    if args.info:
        meta = dvf_service.get_metadata()
        print("\n=== Base DVF locale ===")
        print(f"  Dernière mise à jour : {meta.get('last_update', 'Jamais')}")
        print(f"  Transactions indexées : {meta.get('total_mutations', 0):,}")
        print(f"  Communes couvertes : {meta.get('total_communes', 0):,}")
        print(f"  Période : {meta.get('years', 'N/A')}")
        print(f"  Source : {meta.get('data_source', 'N/A')}")
        print(f"  Besoin de mise à jour : {'Oui' if dvf_service.needs_update() else 'Non'}")
        return

    print("=" * 60)
    print("  MISE À JOUR DE LA BASE DVF LOCALE")
    print("  Source : DGFiP - data.gouv.fr")
    print("=" * 60)

    if not args.skip_download:
        print("\n[1/2] Téléchargement des fichiers DVF...\n")
        result = dvf_service.update_all(args.years)
    else:
        print("\n[1/2] Téléchargement ignoré (--skip-download)")
        result = dvf_service.build_sqlite_index(args.years)
        result = {"index": result}

    meta = result.get("index", {})
    print("\n" + "=" * 60)
    print("  RÉSULTAT DE LA MISE À JOUR")
    print("=" * 60)
    print(f"  ✓ {meta.get('total_mutations', 0):,} transactions indexées")
    print(f"  ✓ {meta.get('total_communes', 0):,} communes couvertes")
    print(f"  ✓ Période : {meta.get('years', 'N/A')}")
    print(f"  ✓ Dernière mise à jour : {meta.get('last_update', 'N/A')}")
    print("=" * 60)
    print("\nLes analyses bancaires utiliseront désormais ces données réelles DGFiP.")


if __name__ == "__main__":
    main()
