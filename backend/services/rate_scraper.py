"""
Scraper de taux immobiliers en temps reel.

Sources gratuites (par ordre de priorite) :
1. MeilleurTaux.com  - barometre hebdomadaire (source principale)
2. Banque de France   - API Webstat SDMX (si disponible)
3. Env vars / defaut  - valeurs configurees dans .env ou valeurs par defaut

Cache : les taux sont stockes dans backend/data/processed/rates_cache.json
        et re-scrappes au maximum 1 fois par jour pour eviter les abus.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Optional

import requests

logger = logging.getLogger(__name__)

# ── Chemins ──────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "data", "processed")
CACHE_PATH = os.path.join(CACHE_DIR, "rates_cache.json")

# ── Parametres ───────────────────────────────────────────────────────────────
CACHE_TTL_HOURS = 720  # Re-scraper au max 1x par mois (source MeilleurTaux hebdomadaire)
HTTP_TIMEOUT = 10       # Timeout pour les appels HTTP

# ── User-Agent HTTP (requis par certains sites) ──────────────────────────────
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ── URLs ─────────────────────────────────────────────────────────────────────
MEILLEURTAUX_URL = "https://www.meilleurtaux.com/credit-immobilier/barometre-des-taux.html"

# ── Taux par defaut (juillet 2026) ───────────────────────────────────────────
_DEFAULT_RATES = {
    "taux_directeur_bce": 2.65,
    "taux_base_15_ans": 3.53,
    "taux_base_20_ans": 3.60,
    "taux_base_25_ans": 3.69,
    "taux_excellent_15_ans": 3.00,
    "taux_excellent_20_ans": 3.10,
    "taux_excellent_25_ans": 3.20,
    "date_publication": "2026-07-27",
    "source": "MeilleurTaux (barometre juillet 2026)",
}


def _scrape_meilleurtaux() -> Optional[dict]:
    """Scrape les taux immobiliers depuis MeilleurTaux.com.

    Cherche le tableau des taux dans le HTML en utilisant des motifs
    textuels comme '15 ans', '20 ans', '25 ans' suivis de pourcentages.

    Returns:
        dict | None: Taux trouves, ou None si echec
    """
    try:
        resp = requests.get(MEILLEURTAUX_URL, headers=HTTP_HEADERS, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except Exception as e:
        logger.warning(f"MeilleurTaux inaccessible : {e}")
        return None

    # Chercher le tableau des taux dans le HTML
    # On cherche le TITRE du tableau puis les valeurs
    # Methode: nettoyer les balises HTML et chercher le pattern dans le texte visible

    # 1. Nettoyer les balises HTML pour obtenir le texte visible
    clean_text = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<script[^>]*>.*?</script>', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<style[^>]*>.*?</style>', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text)

    # 2. Chercher les pourcentages dans le texte
    durees = {}
    for d in ["15", "20", "25"]:
        # Chercher "Xd ans" suivi de pourcentages dans les 200 caracteres suivants
        pattern = re.compile(
            r'\b' + re.escape(d) + r'\s*ans?.*?'
            r'(\d+[\.,]?\d*)\s*%.*?'
            r'(\d+[\.,]?\d*)\s*%.*?'
            r'(\d+[\.,]?\d*)\s*%',
            re.IGNORECASE | re.DOTALL
        )
        match = pattern.search(clean_text)
        if match:
            try:
                vals = [
                    float(match.group(i).replace(",", "."))
                    for i in range(1, 4)
                ]
                # Filtrer les valeurs aberrantes (doivent etre entre 1 et 10)
                vals = [v for v in vals if 1.0 <= v <= 10.0]
                if len(vals) == 3:
                    vals.sort(reverse=True)
                    durees[d] = vals
            except (ValueError, IndexError):
                pass

    if not durees:
        logger.warning("Aucun tableau de taux trouve sur MeilleurTaux")
        return None

    rates = {}
    for d, vals in durees.items():
        if len(vals) == 3:
            rates[f"taux_base_{d}_ans"] = vals[0]
            rates[f"taux_excellent_{d}_ans"] = vals[2]

    if rates:
        rates["date_publication"] = datetime.now().strftime("%Y-%m-%d")
        rates["source"] = f"MeilleurTaux (barometre {rates['date_publication']})"
        logger.info(f"Taux MeilleurTaux recuperes : {rates}")
        return rates

    logger.warning("Impossible de parser les taux MeilleurTaux")
    return None


# TODO: Ajouter _scrape_banque_france() quand l'API Banque de France sera documentee
# Actuellement, les taux sont obtenus via MeilleurTaux (source principale)


def get_cached_rates() -> dict:
    """Retourne les taux depuis le cache local (fichier JSON).

    Returns:
        dict: Taux en cache, ou dict vide si fichier inexistant/corrompu
    """
    if not os.path.exists(CACHE_PATH):
        return {}

    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Erreur lecture cache taux : {e}")
        return {}


def save_rates_cache(rates: dict) -> None:
    """Sauvegarde les taux dans le cache local.

    Args:
        rates: Dictionnaire des taux a sauvegarder
    """
    os.makedirs(CACHE_DIR, exist_ok=True)
    rates["_cached_at"] = datetime.now().isoformat()
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(rates, f, ensure_ascii=False, indent=2)
        logger.info(f"Taux sauvegardes dans {CACHE_PATH}")
    except OSError as e:
        logger.error(f"Erreur ecriture cache taux : {e}")


def needs_refresh(cached: dict) -> bool:
    """Verifie si le cache a besoin d'etre rafraichi.

    Args:
        cached: Taux en cache

    Returns:
        bool: True si le cache est expire ou inexistant
    """
    if not cached:
        return True

    cached_at = cached.get("_cached_at")
    if not cached_at:
        return True

    try:
        last = datetime.fromisoformat(cached_at)
        delta = datetime.now() - last
        return delta.total_seconds() > CACHE_TTL_HOURS * 3600
    except (ValueError, TypeError):
        return True


def fetch_live_rates(force: bool = False) -> dict:
    """Recupere les taux en priorite depuis le scraping, sinon depuis le cache.

    Ordre de priorite :
    1. MeilleurTaux (si cache expire ou force=True)
    2. Cache local
    3. Valeurs par defaut

    Args:
        force: Si True, force un rafraichissement meme si le cache est recent

    Returns:
        dict: Taux avec metadonnees
    """
    cached = get_cached_rates()

    if force or needs_refresh(cached):
        logger.info("Rafraichissement des taux...")

        # 1. Essayer MeilleurTaux
        rates = _scrape_meilleurtaux()
        if rates:
            save_rates_cache(rates)
            return rates

        # 2. Utiliser le cache meme s'il est un peu vieux
        if cached:
            logger.info("Scraping echoue, utilisation du cache existant")
            return cached

        # 3. Fallback valeurs par defaut
        logger.warning("Taux non disponibles, utilisation des valeurs par defaut")
        rates = dict(_DEFAULT_RATES)
        save_rates_cache(rates)
        return rates

    # Cache recent : l'utiliser
    return cached


def update_env_file(rates: dict, env_path: str = None) -> bool:
    """Met a jour les variables d'environnement TAUX_BASE_* dans le fichier .env.

    Args:
        rates: Taux a ecrire
        env_path: Chemin vers le fichier .env (defaut: backend/.env)

    Returns:
        bool: True si la mise a jour a reussi
    """
    if env_path is None:
        env_path = os.path.join(BASE_DIR, ".env")

    if not os.path.exists(env_path):
        logger.warning(f"Fichier .env introuvable : {env_path}")
        return False

    try:
        # Lire le fichier existant
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Mettre a jour ou ajouter les variables
        env_vars = {
            "TAUX_BASE_15_ANS": rates.get("taux_base_15_ans"),
            "TAUX_BASE_20_ANS": rates.get("taux_base_20_ans"),
            "TAUX_BASE_25_ANS": rates.get("taux_base_25_ans"),
            "TAUX_DATE_PUBLICATION": rates.get("date_publication", ""),
            "TAUX_SOURCE": rates.get("source", ""),
        }

        updated_vars = set()
        new_lines = []
        for line in lines:
            stripped = line.strip()
            matched = False
            for var_name, var_value in env_vars.items():
                if var_value is None:
                    continue
                if stripped.startswith(f"{var_name}="):
                    # Appliquer le quoting si la valeur contient des espaces
                    value_str = str(var_value)
                    if ' ' in value_str or '(' in value_str or ')' in value_str:
                        value_str = f'"{value_str}"'
                    new_lines.append(f"{var_name}={value_str}\n")
                    updated_vars.add(var_name)
                    matched = True
                    break
            if not matched:
                new_lines.append(line)

        # Ajouter les variables manquantes
        for var_name, var_value in env_vars.items():
            if var_value is not None and var_name not in updated_vars:
                value_str = str(var_value)
                # Echapper les espaces avec des guillemets
                if ' ' in value_str or '(' in value_str or ')' in value_str:
                    value_str = f'"{value_str}"'
                new_lines.append(f"{var_name}={value_str}\n")

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f"Fichier .env mis a jour avec les nouveaux taux")
        return True

    except Exception as e:
        logger.error(f"Erreur mise a jour .env : {e}")
        return False


if __name__ == "__main__":
    # Test en ligne de commande
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    print("=== Test du scraper de taux ===")
    rates = fetch_live_rates(force=True)
    print(f"\nTaux trouves :")
    for k, v in rates.items():
        print(f"  {k} = {v}")
    print(f"\nCache : {CACHE_PATH}")
