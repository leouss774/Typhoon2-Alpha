"""Taux directeurs bancaires — France.
Les taux sont lus depuis le cache du scraper (MeilleurTaux, mis a jour
chaque semaine) ou depuis les variables d'environnement.

Sources (par ordre de priorite) :
1. Cache du scraper  -> backend/data/processed/rates_cache.json (mis a jour automatiquement)
2. Variables .env     -> TAUX_BASE_15_ANS, TAUX_BASE_20_ANS, TAUX_BASE_25_ANS
3. Valeurs par defaut -> Banque de France / MeilleurTaux (juillet 2026)
"""

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ── Taux directeurs (configurables via .env) ──────────────────────────────
# Valeurs par defaut : Banque de France - Observatoire des credits (juillet 2026)
_TAUX_BASE = {
    "taux_directeur_bce": float(os.getenv("TAUX_DIRECTEUR_BCE", "2.65")),
    "taux_base_15_ans": float(os.getenv("TAUX_BASE_15_ANS", "3.15")),
    "taux_base_20_ans": float(os.getenv("TAUX_BASE_20_ANS", "3.50")),
    "taux_base_25_ans": float(os.getenv("TAUX_BASE_25_ANS", "3.70")),
    "date_publication": os.getenv("TAUX_DATE_PUBLICATION", "2026-07-15"),
    "source": os.getenv("TAUX_SOURCE", "Banque de France - Observatoire Credits Logement"),
}

# Taux moyens du marche (pour comparaison concurrentielle)
# Source : CSA / Meilleurtaux / Empruntis
_TAUX_MARCHE = {
    "taux_moyen_15_ans": float(os.getenv("TAUX_MARCHE_15_ANS", "3.35")),
    "taux_moyen_20_ans": float(os.getenv("TAUX_MARCHE_20_ANS", "3.70")),
    "taux_moyen_25_ans": float(os.getenv("TAUX_MARCHE_25_ANS", "3.95")),
    "date_publication": os.getenv("TAUX_MARCHE_DATE_PUBLICATION", "2026-07-15"),
    "source": os.getenv("TAUX_MARCHE_SOURCE", "CSA / Meilleurtaux (moyenne nationale)"),
}

# Seuils de la grille actuarielle (calcul du risque)
GRILLE_ACTUARIELLE = {
    "seuil_critique": int(os.getenv("SEUIL_RISQUE_CRITIQUE", "80")),
    "seuil_eleve": int(os.getenv("SEUIL_RISQUE_ELEVE", "60")),
    "seuil_modere": int(os.getenv("SEUIL_RISQUE_MODERE", "30")),
    "decote_critique_pct": int(os.getenv("DECOTE_CRITIQUE_PCT", "15")),
    "decote_eleve_pct": int(os.getenv("DECOTE_ELEVE_PCT", "10")),
    "decote_modere_pct": int(os.getenv("DECOTE_MODERE_PCT", "5")),
    "decote_faible_pct": int(os.getenv("DECOTE_FAIBLE_PCT", "0")),
    "majo_critique": float(os.getenv("MAJO_CRITIQUE", "0.50")),
    "majo_eleve": float(os.getenv("MAJO_ELEVE", "0.20")),
    "majo_modere": float(os.getenv("MAJO_MODERE", "0.05")),
    "majo_faible": float(os.getenv("MAJO_FAIBLE", "-0.10")),
}


def _try_scraper_cache() -> dict | None:
    """Tente de recuperer les taux depuis le cache du scraper.

    Le cache est mis a jour automatiquement chaque semaine par le scraper
    (backend/services/rate_scraper.py). Si les taux sont presents et
    recents, ils sont prioritaires sur les valeurs du .env.

    Returns:
        dict | None: Taux du cache, ou None si indisponible
    """
    try:
        from services.rate_scraper import fetch_live_rates
        rates = fetch_live_rates(force=False)
        if rates and "taux_base_20_ans" in rates:
            logger.info(f"Taux issus du scraper : {rates.get('source', 'N/A')}")
            return rates
    except ImportError:
        logger.debug("rate_scraper non disponible, utilisation du .env")
    except Exception as e:
        logger.debug(f"Erreur acces cache scraper : {e}")
    return None


def get_bank_rates() -> dict:
    """Retourne les taux directeurs bancaires avec date de publication.

    Ordre de priorite :
    1. Cache du scraper MeilleurTaux (mis a jour chaque semaine)
    2. Variables d'environnement (.env)
    3. Valeurs par defaut (Banque de France juillet 2026)

    Les variables d'environnement configurables :
    - TAUX_BASE_20_ANS : taux de reference pour un pret sur 20 ans
    - TAUX_DIRECTEUR_BCE : taux directeur de la Banque Centrale Europeenne
    - TAUX_DATE_PUBLICATION : date de publication des taux

    Returns:
        dict: Taux directeurs avec metadonnees
    """
    # 1. Priorite : cache du scraper (donnees temps reel)
    scraper_rates = _try_scraper_cache()
    if scraper_rates and scraper_rates.get("taux_base_20_ans"):
        return _build_rates_dict(scraper_rates)

    # 2. Fallback : .env / valeurs par defaut
    return _build_rates_dict(_TAUX_BASE)


def _build_rates_dict(base: dict) -> dict:
    """Construit le dictionnaire final des taux avec metadonnees."""
    return {
        **base,
        "date_mise_a_jour": datetime.now(timezone.utc).isoformat(),
        "grille_actuarielle": GRILLE_ACTUARIELLE,
    }


def get_market_rates() -> dict:
    """Retourne les taux moyens du marche pour comparaison concurrentielle.

    Returns:
        dict: Taux du marche avec metadonnees
    """
    return {
        **_TAUX_MARCHE,
        "date_mise_a_jour": datetime.now(timezone.utc).isoformat(),
    }


def get_actuarial_grid() -> dict:
    """Retourne la grille actuarielle complete (seuils et coefficients).

    Utilisee par calculate_risk_premium() dans bank_tools.py.
    Les seuils sont configurables via les variables d'environnement.

    Returns:
        dict: Grille complete avec seuils et decotes/majorations
    """
    return dict(GRILLE_ACTUARIELLE)