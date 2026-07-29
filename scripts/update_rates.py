"""
Script de mise a jour des taux immobiliers.

Usage :
    python scripts/update_rates.py               # Scrape et met a jour
    python scripts/update_rates.py --force        # Force le rafraichissement
    python scripts/update_rates.py --info         # Affiche les taux actuels
    python scripts/update_rates.py --update-env   # Scrape + met a jour le .env

Ce script recupere les taux immobiliers depuis MeilleurTaux.com
(barometre hebdomadaire gratuit) et met a jour le cache local.

Sources :
- MeilleurTaux.com  (source principale, gratuite, mise a jour chaque semaine)
- Banque de France   (API Webstat SDMX, si disponible)
- Valeurs par defaut (juillet 2026)
"""

import argparse
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("update_rates")


def main():
    parser = argparse.ArgumentParser(
        description="Mise a jour des taux immobiliers depuis MeilleurToux"
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Force le rafraichissement meme si le cache est recent"
    )
    parser.add_argument(
        "--info", action="store_true",
        help="Affiche les taux actuels sans rafraichir"
    )
    parser.add_argument(
        "--update-env", action="store_true",
        help="Scrape et met a jour le fichier .env avec les nouveaux taux"
    )
    args = parser.parse_args()

    from backend.services.rate_scraper import fetch_live_rates, get_cached_rates, update_env_file

    if args.info:
        cached = get_cached_rates()
        print("\n=== Taux actuellement en cache ===")
        if cached:
            for k, v in cached.items():
                if not k.startswith("_"):
                    print(f"  {k} = {v}")
            print(f"  Cache depuis : {cached.get('_cached_at', 'N/A')}")
        else:
            print("  Aucun taux en cache.")
            print("  Executez 'python scripts/update_rates.py' pour rafraichir.")
        return

    print("=" * 60)
    print("  MISE A JOUR DES TAUX IMMOBILIERS")
    print("  Source : MeilleurTaux.com (barometre hebdomadaire)")
    print("=" * 60)

    print("\nRafraichissement des taux...\n")
    rates = fetch_live_rates(force=args.force or args.update_env)

    print(f"\nTaux recuperes :")
    for k, v in rates.items():
        if not k.startswith("_"):
            print(f"  {k} = {v}")
    print(f"\n  Source : {rates.get('source', 'N/A')}")
    print(f"  Date : {rates.get('date_publication', 'N/A')}")

    # Optionnel : mettre a jour le .env
    if args.update_env:
        print("\nMise a jour du fichier .env...")
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend", ".env")
        if os.path.exists(env_path):
            ok = update_env_file(rates, env_path)
            if ok:
                print(f"  [OK] Fichier .env mis a jour : {env_path}")
            else:
                print(f"  [ERREUR] Impossible de mettre a jour {env_path}")
        else:
            print(f"  [INFO] .env introuvable : {env_path}")
            print("  Les taux sont disponibles via le cache pour le scraping.")

    print("\n" + "=" * 60)
    print("  Les analyses bancaires utilisent desormais ces taux actualises.")
    print("=" * 60)


if __name__ == "__main__":
    main()
