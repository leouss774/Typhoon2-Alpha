# -*- coding: utf-8 -*-
"""
Service de matching optimisé avec cache, parallélisation et fallbacks.
Point d'entrée unique pour l'API FastAPI.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import requests

from app.core.config import settings
from app.matching.cache import entreprise_cache, rge_cache
from app.matching.generate_rapport_artisans import (
    CATEGORIES_NON_RGE,
    RECOMMANDATION_VERS_DOMAINE_ADEME,
    _classifier_recommandation,
    _enrichir_lien_entreprise,
    _extraire_priorite,
    formater_resultats_non_rge,
)
from app.matching.match_artisans_rge import calculer_score_objectif, haversine_km, rechercher_entreprises_rge, rechercher_entreprises_rge_zone_elargie

logger = logging.getLogger(__name__)

API_RECHERCHE_ENTREPRISES = "https://recherche-entreprises.api.gouv.fr/search"

# ── Fallback NAF pour les catégories non-RGE ────────────────
NAF_FALLBACKS: dict[str, list[str]] = {
    "71.12B": ["71.12A", "71.11Z", "74.90B"],
    "43.99C": ["43.91A", "43.22A", "43.21A"],
    "43.21A": ["43.22A", "43.99C", "33.14Z"],
    "43.22A": ["43.21A", "43.99C", "33.12Z"],
    "43.91A": ["43.99A", "43.99C", "43.22A"],
    "43.99A": ["43.99C", "43.91A", "43.21A"],
}


# ── Cache-aware ADEME RGE search ────────────────────────────
def rechercher_rge_avec_cache(code_postal: str, domaine: str, limite: int = 20) -> list[dict[str, Any]]:
    """Cherche des entreprises RGE avec cache + fallback département."""
    cache_key = f"{code_postal}|{domaine}"
    cached = rge_cache.get(cache_key)
    if cached is not None:
        logger.debug("  [cache RGE] hit for %s", cache_key)
        return cached

    try:
        resultats = rechercher_entreprises_rge(code_postal, domaine, limite)
        if not resultats:
            logger.info("  [RGE] fallback département %s pour %s", code_postal[:2], domaine)
            resultats = rechercher_entreprises_rge_zone_elargie(code_postal[:2], domaine, limite)
        rge_cache.set(cache_key, resultats)
        return resultats
    except requests.RequestException as exc:
        logger.warning("  [RGE] requête échouée pour %s: %s", cache_key, exc)
        return []


# ── Cache-aware Recherche Entreprises search ────────────────
def rechercher_non_rge_avec_cache(code_postal: str, code_naf: str, limite: int = 10) -> list[dict[str, Any]]:
    """Cherche des entreprises non-RGE avec cache + fallback NAF."""
    cache_key = f"{code_postal}|{code_naf}"
    cached = entreprise_cache.get(cache_key)
    if cached is not None:
        logger.debug("  [cache ENT] hit for %s", cache_key)
        return cached

    params = {
        "code_postal": code_postal,
        "activite_principale": code_naf,
        "etat_administratif": "A",
        "per_page": limite,
    }
    try:
        resp = requests.get(API_RECHERCHE_ENTREPRISES, params=params, timeout=30)
        resp.raise_for_status()
        resultats = resp.json().get("results", [])
        entreprise_cache.set(cache_key, resultats)

        # Fallback NAF si pas assez de résultats
        if len(resultats) < 3:
            fallbacks = NAF_FALLBACKS.get(code_naf, [])
            for naf_fb in fallbacks:
                fb_key = f"{code_postal}|{naf_fb}"
                fb_cached = entreprise_cache.get(fb_key)
                if fb_cached is not None:
                    logger.debug("  [cache ENT] fallback NAF %s (cached)", naf_fb)
                    resultats.extend(fb_cached[:5])
                    continue
                fb_params = {**params, "activite_principale": naf_fb}
                try:
                    fb_resp = requests.get(API_RECHERCHE_ENTREPRISES, params=fb_params, timeout=30)
                    fb_resp.raise_for_status()
                    fb_results = fb_resp.json().get("results", [])
                    entreprise_cache.set(fb_key, fb_results)
                    resultats.extend(fb_results[:5])
                except requests.RequestException:
                    continue
                if len(resultats) >= limite * 2:
                    break

        return resultats
    except requests.RequestException as exc:
        logger.warning("  [ENT] requête échouée pour %s: %s", cache_key, exc)
        return []


# ── Traitement d'une recommandation (synchrone, exécuté dans un thread) ──
def traiter_une_recommandation(
    reco: dict[str, Any],
    code_postal: str,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Traite une seule recommandation (RGE ou non-RGE)."""
    cle = reco.get("cle", "")
    priorite = _extraire_priorite(reco)

    metadonnees = {
        k: reco[k] for k in ("zone_origine", "risques_origine", "mesure_originale", "cout_estime")
        if k in reco
    }

    # ── Cas RGE ──
    if cle in RECOMMANDATION_VERS_DOMAINE_ADEME:
        domaine = RECOMMANDATION_VERS_DOMAINE_ADEME[cle]
        brutes = rechercher_rge_avec_cache(code_postal, domaine)
        entreprises = []
        for ent in brutes:
            score_info = calculer_score_objectif(ent, code_postal, lat, lon)
            enriched = {**ent, **score_info}
            _enrichir_lien_entreprise(enriched)
            entreprises.append(enriched)
        entreprises.sort(key=lambda e: e.get("score_objectif_sur_100", 0), reverse=True)
        return {
            "cle": cle, "categorie": "rge", "priorite": priorite,
            "domaine_recherche": domaine, "entreprises": entreprises,
            "annuaire_reference": {
                "organisme": "France Renov' - annuaire officiel RGE",
                "url": "https://france-renov.gouv.fr/annuaires-professionnels",
            },
            **metadonnees,
        }

    # ── Cas non-RGE ──
    if cle in CATEGORIES_NON_RGE:
        config = CATEGORIES_NON_RGE[cle]
        brutes = rechercher_non_rge_avec_cache(code_postal, config["code_naf"])
        entreprises = formater_resultats_non_rge(brutes, code_postal)
        return {
            "cle": cle, "categorie": "non_rge", "priorite": priorite,
            "libelle": config["libelle"], "code_naf_recherche": config["code_naf"],
            "entreprises": entreprises, "annuaire_reference": config["annuaire_reference"],
            **metadonnees,
        }

    return {
        "cle": cle, "categorie": "inconnue", "priorite": priorite,
        "erreur": f"Clé '{cle}' non reconnue",
        **metadonnees,
    }


# ── Traitement parallèle de toutes les recommandations ──────
async def matching_parallele(
    recommandations: list[dict[str, Any]],
    code_postal: str,
    lat: float | None = None,
    lon: float | None = None,
) -> list[dict[str, Any]]:
    """Exécute le matching de toutes les recommandations EN PARALLÈLE
    via un ThreadPoolExecutor (car les appels API sont synchrones)."""
    loop = asyncio.get_running_loop()
    tasks = [
        loop.run_in_executor(None, traiter_une_recommandation, reco, code_postal, lat, lon)
        for reco in recommandations
    ]
    results = await asyncio.gather(*tasks)
    return list(results)


# ── Interface publique ──────────────────────────────────────
async def run_matching(
    recommandations_input: list[dict[str, Any]],
    code_postal: str,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Point d'entrée principal : traite toutes les recommandations en parallèle
    et retourne un rapport structuré avec résumé."""
    resultats = await matching_parallele(recommandations_input, code_postal, lat, lon)

    total_entreprises = sum(len(r.get("entreprises", [])) for r in resultats)
    compteur = {"rge": 0, "non_rge": 0, "inconnue": 0}
    for r in resultats:
        cat = r.get("categorie", "inconnue")
        compteur[cat] = compteur.get(cat, 0) + 1

    return {
        "recommandations_traitees": resultats,
        "resume": {
            "total_recommandations_traitees": len(resultats),
            "total_entreprises_trouvees": total_entreprises,
            "details_categories": compteur,
        },
    }
