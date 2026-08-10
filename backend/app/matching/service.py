# -*- coding: utf-8 -*-
"""
Service de matching optimisé avec cache, parallélisation et fallbacks.
Point d'entrée unique pour l'API FastAPI.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any
from urllib.parse import urlparse

import requests

from app.artisans.site_finder import EXCLUDED_HOSTS
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
ANNUAIRE_HOSTS = EXCLUDED_HOSTS

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
        k: reco[k] for k in ("recommendation_id", "zone_origine", "risques_origine", "mesure_originale", "cout_estime")
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


def _site_entreprise(value: Any) -> str | None:
    """Accepte exclusivement un domaine propre a l'entreprise, jamais un annuaire."""
    raw = str(value or "").strip()
    if not raw:
        return None
    url = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    host = (urlparse(url).hostname or "").lower().removeprefix("www.")
    if not host or "." not in host or any(host == item or host.endswith(f".{item}") for item in ANNUAIRE_HOSTS):
        return None
    return url


def _enrichir_simples(resultats: list[dict[str, Any]], limite: int) -> None:
    """Expose chaque entreprise avec les données natives disponibles.

    - `site_officiel` : conservé s'il existe dans les registres source (RGE / ADEME)
      et passe le filtre `_site_entreprise` (excluant les domaines d'annuaires).
    - `site_annuaire` : repli systématique vers la fiche officielle
      `https://annuaire-entreprises.data.gouv.fr/entreprise/{identifiant}` si
      aucun site officiel propre n'est disponible (bouton 'Fiche entreprise' dans le frontend).
    - `telephone` et `email` : conservés s'ils existent dans la source native.
    - Aucun appel web externalisé (Mistral web_search) n'est effectué, afin de
      préserver le quota API Mistral pour les fonctionnalités d'analyse cœur.
    - Les champs internes (score, lien de fiche, site_internet) sont nettoyés.
    """
    for resultat in resultats:
        entreprises = (resultat.get("entreprises") or [])[:limite]
        resultat["entreprises"] = entreprises  # cap réel de la réponse (Top N)
        for entreprise in entreprises:
            site = _site_entreprise(entreprise.get("site_officiel") or entreprise.get("site_internet"))
            telephone = entreprise.get("telephone")
            email = entreprise.get("email")

            entreprise["site_officiel"] = site
            entreprise["telephone"] = telephone
            entreprise["email"] = email

            # Repli : sans site propre, on pointe vers la fiche officielle de
            # l'annuaire public (jamais un faux lien) — le bouton « Fiche entreprise »
            # reste disponible pour chaque artisan.
            if not site:
                identifiant = entreprise.get("siren") or (entreprise.get("siret") or "")[:9]
                if identifiant:
                    entreprise["site_annuaire"] = f"https://annuaire-entreprises.data.gouv.fr/entreprise/{identifiant}"

            for key in (
                "site_internet", "lien_fiche_officielle",
                "profil_verifie", "site_verifie", "contact_verifie",
                "score_objectif_sur_100", "details_score",
            ):
                entreprise.pop(key, None)

        if not resultat.get("erreur"):
            if not entreprises:
                resultat["notice"] = "Aucune entreprise active n'a ete trouvee pour cette recommandation."
            elif not any(e.get("site_officiel") or e.get("telephone") or e.get("email") for e in entreprises):
                resultat["notice"] = (
                    "Entreprises actives identifiees dans les registres publics ; "
                    "leurs coordonnees et leur site restent a confirmer."
                )


# ── Interface publique ──────────────────────────────────────
async def run_matching(
    recommandations_input: list[dict[str, Any]],
    code_postal: str,
    lat: float | None = None,
    lon: float | None = None,
    limite_entreprises: int = 5,
) -> dict[str, Any]:
    """Point d'entrée principal : traite toutes les recommandations en parallèle
    et retourne un rapport structuré avec résumé."""
    resultats = await matching_parallele(recommandations_input, code_postal, lat, lon)
    _enrichir_simples(resultats, limite_entreprises)

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
