"""
Scraper de taux immobiliers en temps reel.

Sources gratuites (par ordre de priorite) :
1. MeilleurTaux.com  - barometre hebdomadaire (source principale)
2. Banque de France   - API Webstat OpenDataSoft (cross-verification)
3. Cache local        - backend/data/processed/rates_cache.json
4. Env vars / defaut  - valeurs configurees dans .env ou valeurs par defaut

La source Banque de France est utilisee pour CROSS-VERIFIER les taux
MeilleurTaux. Si l'ecart entre les deux sources depasse 0.5%,
un avertissement est emis et la valeur la plus conservative est utilisee.

Cache : les taux sont stockes dans backend/data/processed/rates_cache.json
        et re-scrappes au maximum 1 fois par mois (TTL 720h).
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
CACHE_TTL_HOURS = 720  # Re-scraper au max 1x par mois
HTTP_TIMEOUT = 10       # Timeout pour les appels HTTP

# ── User-Agent HTTP (requis par certains sites) ──────────────────────────────
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ── URLs ─────────────────────────────────────────────────────────────────────
MEILLEURTAUX_URL = "https://www.meilleurtaux.com/credit-immobilier/barometre-des-taux.html"

# Banque de France - API Webstat OpenDataSoft (explore v2.1)
# Documentation : https://webstat.banque-france.fr/fr/pages/guide-migration-api/
BDF_API_URL = "https://webstat.banque-france.fr/api/explore/v2.1/"
BDF_CATALOG_URL = BDF_API_URL + "catalog/datasets"

# ── Series MIR1 recherchees pour les taux de credit immobilier ───────────────
# L'API catalogue est interrogee dynamiquement avec les mots-cles ci-dessous.
# Les series MIR1 contiennent les taux d'interet des IMF pour la France.
BDF_SEARCH_KEYWORDS = [
    "credit habitat nouveaux taux",
    "MIR1 FR logement",
    "taux credit immobilier France",
]

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

    # Nettoyer les balises HTML pour obtenir le texte visible
    clean_text = re.sub(r'<head[^>]*>.*?</head>', '', html, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<script[^>]*>.*?</script>', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<style[^>]*>.*?</style>', '', clean_text, flags=re.DOTALL | re.IGNORECASE)
    clean_text = re.sub(r'<[^>]+>', ' ', clean_text)
    clean_text = re.sub(r'\s+', ' ', clean_text)

    # Chercher les pourcentages dans le texte
    durees = {}
    for d in ["15", "20", "25"]:
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


# ── Source Banque de France (Webstat API OpenDataSoft) ──────────────────────


def _scrape_banque_france() -> Optional[dict]:
    """Recupere les taux de credit immobilier depuis l'API Webstat Banque de France.

    Utilise l'API OpenDataSoft explore v2.1 du portail Webstat pour interroger
    le catalogue des series MIR (Monetary Interest Rates).

    La fonction cherche les series correspondant aux taux des credits nouveaux
    a l'habitat (housing loans, new business) pour la France.

    Returns:
        dict | None: Taux BDF trouves, ou None si echec
    """
    try:
        # 1. Chercher les datasets MIR1 dans le catalogue
        # Requete large : on cherche TOUTES les series MIR liees au credit
        resp = requests.get(
            f"{BDF_CATALOG_URL}?q=MIR&limit=50&lang=fr",
            headers=HTTP_HEADERS,
            timeout=HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        catalog = resp.json()
    except requests.RequestException as e:
        logger.warning(f"Banque de France API inaccessible : {e}")
        return None
    except Exception as e:
        logger.warning(f"Banque de France API erreur inattendue : {e}")
        return None

    results = catalog.get("results", [])
    if not results:
        logger.warning("BDF : catalogue vide")
        return None

    # 2. Filtrer les series pertinentes
    # On cherche les series dont le titre contient des mots-cles credit/logement
    # ET qui ont des unites de pourcentage (PC, PCH, etc.)
    pc_series = []
    for r in results:
        metas = r.get("metas", {})
        if not isinstance(metas, dict):
            continue
        custom = metas.get("custom", {})
        if not isinstance(custom, dict):
            continue

        series_key = custom.get("series_key", "")
        unit = custom.get("series_unit", "")
        last_obs = custom.get("series_last_two_obs_values", "")
        title_fr = custom.get("series_title_fr") or ""
        title_en = custom.get("series_title_en") or ""
        title = title_fr or title_en

        # Chercher les unites de pourcentage (PC, PCH, PC_*) et des mots-cles credit
        is_pct = unit.startswith("PC") if unit else False
        has_credit = any(kw in title.lower() for kw in ["credit", "taux", "interest", "logement", "habitat", "housing", "loan"])
        has_data = bool(last_obs)

        if is_pct and has_credit and has_data:
            pc_series.append({
                "key": series_key,
                "title": title,
                "unit": unit,
                "last_obs": last_obs,
                "dataset_id": r.get("dataset_id", ""),
            })

    if not pc_series:
        # Logguer les premieres series trouvees pour debug
        debug_titles = []
        for r in results[:5]:
            m = r.get("metas", {}).get("custom", {})
            debug_titles.append(m.get("series_title_fr", "?")[:60])
        logger.warning(
            f"BDF : aucune serie pertinente trouvee dans {len(results)} resultats. "
            f"Exemples: {debug_titles}"
        )
        return None

    # 3. Extraire les valeurs et mapper les durees
    bdf_rates = {}
    bdf_taux_vals = []  # pour calculer une moyenne

    for s in pc_series:
        last_raw = s["last_obs"]
        parts = last_raw.split(",")
        if not parts:
            continue

        try:
            last_val = float(parts[-1].strip())
        except (ValueError, IndexError):
            continue

        if not (0 < last_val <= 100):
            continue

        title = s["title"].lower()
        # Chercher la maturite avec regex: "X ans" dans le titre
        # Accepte "5 ans", "15 ans", "20 ans", "1 an", etc.
        # Note: "plus de 5 ans" est deja capture par (\d{1,2})\s*ans? -> years=5
        maturity_match = re.search(r'(\d{1,2})\s*ans?', title)
        if maturity_match:
            years = int(maturity_match.group(1))
            if years <= 15:
                bdf_rates["bdf_taux_15_ans"] = last_val
            elif years <= 20:
                bdf_rates["bdf_taux_20_ans"] = last_val
            else:
                bdf_rates["bdf_taux_25_ans"] = last_val

        # Accumuler pour la moyenne
        if "logement" in title or "habitat" in title or "credit" in title:
            bdf_taux_vals.append(last_val)
        elif "tous" in title and "credit" in title:
            bdf_taux_vals.append(last_val)

    # Verifier qu'on a au moins un taux avec duree exploitable
    has_duration_key = any(k in bdf_rates for k in ["bdf_taux_15_ans", "bdf_taux_20_ans", "bdf_taux_25_ans"])
    if not has_duration_key:
        logger.info("BDF : valeurs trouvees mais aucune correspondance de duree exploitable")
        return None

    # Calculer la mediane apres avoir confirme qu'on a des donnees utilisables
    if bdf_taux_vals:
        bdf_taux_vals.sort()
        mid = len(bdf_taux_vals) // 2
        bdf_rates["bdf_taux_moyen"] = bdf_taux_vals[mid] if len(bdf_taux_vals) > 2 else (
            sum(bdf_taux_vals) / len(bdf_taux_vals)
        )

    # Ajouter les metadonnees
    bdf_rates["bdf_source"] = "Banque de France (Webstat MIR1)"
    bdf_rates["bdf_date_publication"] = datetime.now().strftime("%Y-%m-%d")
    bdf_rates["bdf_nb_series"] = len(pc_series)
    bdf_rates["bdf_nb_taux_extraits"] = len(bdf_taux_vals)

    logger.info(f"Taux Banque de France recuperes : {bdf_rates}")
    return bdf_rates


# ── Cross-verification MeilleurTaux vs Banque de France ──────────────────────


def _cross_verify_rates(mt_rates: dict, bdf_rates: dict | None) -> dict:
    """Croise les taux MeilleurTaux avec les taux Banque de France.

    Si l'ecart entre les deux sources depasse SEUIL_ALERTE_PCT,
    un avertissement est emis dans les logs et le cache.
    La valeur la plus conservative (taux le plus eleve) est utilisee.

    Args:
        mt_rates: Taux provenant de MeilleurTaux
        bdf_rates: Taux provenant de la Banque de France (ou None)

    Returns:
        dict: Taux verifies avec metadonnees de fiabilite
    """
    SEUIL_ALERTE_PCT = 0.5

    if not bdf_rates:
        mt_rates["cross_verified"] = False
        mt_rates["cross_source"] = "Aucune (BDF indisponible)"
        return mt_rates

    divergences = []
    # Mapper les durees entre MT et BDF
    for d in ["15", "20", "25"]:
        mt_key = f"taux_base_{d}_ans"
        bdf_key = f"bdf_taux_{d}_ans"

        mt_val = mt_rates.get(mt_key)
        bdf_val = bdf_rates.get(bdf_key)

        if mt_val is not None and bdf_val is not None:
            ecart = abs(mt_val - bdf_val)
            if ecart > SEUIL_ALERTE_PCT:
                divergences.append({
                    "duree": f"{d} ans",
                    "meilleurtaux": mt_val,
                    "banque_france": bdf_val,
                    "ecart": round(ecart, 2),
                })
                # Prendre la valeur la plus conservative
                mt_rates[mt_key] = max(mt_val, bdf_val)
                logger.warning(
                    f"Divergence {d} ans : MT={mt_val}% vs BDF={bdf_val}% "
                    f"(ecart={ecart:.2f}%) - utilisation taux le plus eleve"
                )

    # Verifier le taux moyen (fallback si pas de correspondance par duree)
    mt_avg = mt_rates.get("taux_base_20_ans")
    bdf_avg = bdf_rates.get("bdf_taux_moyen")
    if mt_avg and bdf_avg and abs(mt_avg - bdf_avg) > SEUIL_ALERTE_PCT:
        divergences.append({
            "duree": "moyen",
            "meilleurtaux": mt_avg,
            "banque_france": bdf_avg,
            "ecart": round(abs(mt_avg - bdf_avg), 2),
        })
        # Utiliser le taux conservatif
        if mt_avg < bdf_avg:
            mt_rates["taux_base_20_ans"] = bdf_avg
            logger.warning(
                f"Divergence taux moyen : MT={mt_avg}% vs BDF={bdf_avg}% - "
                f"utilisation du taux BDF (plus conservatif)"
            )

    mt_rates["cross_verified"] = True
    mt_rates["cross_source"] = f"Banque de France (Webstat MIR1)"
    mt_rates["cross_date"] = bdf_rates.get("bdf_date_publication", "")
    mt_rates["bdf_nb_series"] = bdf_rates.get("bdf_nb_series", 0)

    if divergences:
        mt_rates["cross_divergences"] = divergences
        mt_rates["cross_status"] = "DIVERGENCE"
        logger.warning(
            f"Cross-verification BDF : {len(divergences)} divergence(s) "
            f"detectee(s). Taux conservatifs appliques."
        )
    else:
        mt_rates["cross_status"] = "OK"
        logger.info(
            f"Cross-verification BDF : OK (taux coherents entre les 2 sources)"
        )

    return mt_rates


# ── Gestion du cache ────────────────────────────────────────────────────────


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


# ── Point d'entree principal ─────────────────────────────────────────────────


def fetch_live_rates(force: bool = False) -> dict:
    """Recupere les taux avec cross-verification Banque de France.

    Ordre de priorite :
    1. MeilleurTaux (si cache expire ou force=True)
    2. Banque de France (cross-verification)
    3. Cache local
    4. Valeurs par defaut

    Args:
        force: Si True, force un rafraichissement meme si le cache est recent

    Returns:
        dict: Taux avec metadonnees (source, date, cross-verification)
    """
    cached = get_cached_rates()
    bdf_rates = None  # initialise pour eviter UnboundLocalError

    if force or needs_refresh(cached):
        logger.info("Rafraichissement des taux...")

        # 1. MeilleurTaux (source principale)
        mt_rates = _scrape_meilleurtaux()

        # 2. Banque de France (cross-verification)
        bdf_rates = _scrape_banque_france()

        if mt_rates:
            # Cross-verifier avec BDF
            verified = _cross_verify_rates(mt_rates, bdf_rates)
            save_rates_cache(verified)
            return verified

    if bdf_rates:
        # Fallback BDF si MT indisponible - seulement si on a au moins un taux exploitable
        bdf_15 = bdf_rates.get("bdf_taux_15_ans")
        bdf_20 = bdf_rates.get("bdf_taux_20_ans")
        bdf_25 = bdf_rates.get("bdf_taux_25_ans")
        bdf_has_usable = any(v is not None for v in [bdf_15, bdf_20, bdf_25])

        if bdf_has_usable:
            logger.info("MeilleurTaux indisponible, utilisation des taux BDF")
            bdf_fallback = {
                "taux_base_15_ans": bdf_15 or _DEFAULT_RATES["taux_base_15_ans"],
                "taux_base_20_ans": bdf_20 or _DEFAULT_RATES["taux_base_20_ans"],
                "taux_base_25_ans": bdf_25 or _DEFAULT_RATES["taux_base_25_ans"],
                "date_publication": bdf_rates.get("bdf_date_publication", ""),
                "source": "Banque de France (Webstat MIR1)",
                "cross_source": "Aucune (MT indisponible)",
            }
            save_rates_cache(bdf_fallback)
            return bdf_fallback
        else:
            logger.info("BDF : pas de taux avec duree exploitable pour le fallback")

        # 3. Cache existant meme s'il est vieux
        if cached:
            logger.info("Scraping echoue, utilisation du cache existant")
            return cached

        # 4. Fallback valeurs par defaut
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
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

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
                    value_str = str(var_value)
                    if ' ' in value_str or '(' in value_str or ')' in value_str:
                        value_str = f'"{value_str}"'
                    new_lines.append(f"{var_name}={value_str}\n")
                    updated_vars.add(var_name)
                    matched = True
                    break
            if not matched:
                new_lines.append(line)

        for var_name, var_value in env_vars.items():
            if var_value is not None and var_name not in updated_vars:
                value_str = str(var_value)
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
    print("=== Test du scraper de taux avec cross-verification BDF ===")
    rates = fetch_live_rates(force=True)
    print(f"\nTaux trouves :")
    for k, v in rates.items():
        print(f"  {k} = {v}")
    print(f"\nCache : {CACHE_PATH}")
