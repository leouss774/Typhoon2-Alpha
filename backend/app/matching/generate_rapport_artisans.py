# -*- coding: utf-8 -*-
"""
generate_rapport_artisans.py
===============================
Prend un fichier JSON listant TOUTES les recommandations d'un rapport
(RGE thermique + non-RGE : geotechnique RGA, structure sismique, radon,
drainage/ruissellement) et genere, pour chacune, la meme structure de
resultat que match_artisans_rge.py -- en ajoutant desormais :
  - le lien du site internet de l'entreprise quand disponible (RGE)
  - le lien de l'annuaire professionnel de reference pour les
    categories non couvertes par un label RGE (geotechnique, structure,
    radon, drainage)

Sources reelles utilisees (aucune fabrication) :
  - RGE            : data.ademe.fr (deja utilise par match_artisans_rge.py)
  - Non-RGE        : recherche-entreprises.api.gouv.fr (API officielle,
                      gratuite, sans cle -- Direction Generale des Entreprises)
  - Annuaires pro  : liens verifies vers les organismes de reference

Usage :
    python generate_rapport_artisans.py --json recommandations.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any

import requests

from app.matching.match_artisans_rge import (
    RECOMMANDATION_VERS_DOMAINE_ADEME,
    matcher_recommandation,
)

API_RECHERCHE_ENTREPRISES = "https://recherche-entreprises.api.gouv.fr/search"

# ─────────────────────────────────────────────────────────────
# Categories NON couvertes par le label RGE : code NAF pertinent
# + annuaire professionnel de reference (lien verifie).
# Le code NAF sert a chercher de VRAIES entreprises locales ;
# l'annuaire professionnel est le point d'entree fiable pour
# verifier une vraie qualification metier (contrairement au NAF,
# qui n'atteste que de l'activite declaree, pas d'une competence).
# ─────────────────────────────────────────────────────────────
CATEGORIES_NON_RGE: dict[str, dict[str, Any]] = {
    # ── Risques naturels / structure ──
    "rga_geotechnique": {
        "libelle": "Étude et confortement géotechnique (RGA)",
        "code_naf": "71.12B",  # Ingénierie, études techniques
        "annuaire_reference": {
            "organisme": "USG - Union Syndicale Géotechnique",
            "url": "https://www.usg.asso.fr/annuaire-des-membres/",
            "note": "Annuaire des bureaux d'études géotechniques membres, gage de compétence reconnue par la profession.",
        },
    },
    "sismique_structure": {
        "libelle": "Diagnostic et renforcement parasismique",
        "code_naf": "71.12B",
        "annuaire_reference": {
            "organisme": "CINOV Construction (syndicat des bureaux d'études structure)",
            "url": "https://www.cinov.fr/annuaire-cinov/",
            "note": "Annuaire des bureaux d'ingénierie structure adhérents CINOV.",
        },
    },
    "radon_etancheite": {
        "libelle": "Étanchéité et ventilation anti-radon",
        "code_naf": "43.99C",  # Travaux d'étanchéification
        "annuaire_reference": {
            "organisme": "ASNR — ressources radon (pas de certification d'entreprise en France)",
            "url": "https://www.asnr.fr/",
            "note": "Aucun label d'entreprise spécifique au radon en France : vérifier les références.",
        },
    },
    "ruissellement_drainage": {
        "libelle": "Drainage et gestion du ruissellement pluvial",
        "code_naf": "43.99C",
        "annuaire_reference": {
            "organisme": "CEPRI (guides méthodologiques, pas d'annuaire d'entreprises)",
            "url": "https://cepri.net/",
            "note": "Pas de label national pour ce poste : privilégier une entreprise VRD locale.",
        },
    },
    # ── Métiers du bâtiment (hors RGE) ──
    "electricite": {
        "libelle": "Travaux d'installation électrique",
        "code_naf": "43.21A",
        "annuaire_reference": {
            "organisme": "FFIE (Fédération Française des Intégrateurs Électriciens)",
            "url": "https://www.ffie.fr/annuaire/",
            "note": "Annuaire des électriciens professionnels adhérents FFIE.",
        },
    },
    "plomberie_chauffage": {
        "libelle": "Travaux de plomberie et chauffage",
        "code_naf": "43.22A",
        "annuaire_reference": {
            "organisme": "FFB – Union des Métiers du Génie Climatique",
            "url": "https://umgc.ffbatiment.fr/",
            "note": "Annuaire des professionnels du génie climatique (chauffage, plomberie, sanitaire).",
        },
    },
    "couverture": {
        "libelle": "Travaux de couverture et zinguerie",
        "code_naf": "43.91A",
        "annuaire_reference": {
            "organisme": "FFB – Union des Métiers de la Couverture",
            "url": "https://www.ffbatiment.fr/",
            "note": "Consultez la FFB pour des recommandations de couvreurs professionnels.",
        },
    },
    "maconnerie": {
        "libelle": "Travaux de maçonnerie générale",
        "code_naf": "43.99A",
        "annuaire_reference": {
            "organisme": "FFB – Fédération Française du Bâtiment",
            "url": "https://www.ffbatiment.fr/",
            "note": "Annuaire général des entreprises du bâtiment par région et spécialité.",
        },
    },
}


def rechercher_entreprises_non_rge(code_postal: str, code_naf: str, limite: int = 10) -> list[dict[str, Any]]:
    """Query the official, free 'Recherche d'Entreprises' API by NAF code
    and postal code. Returns real, verifiable company records (SIREN,
    name, address, administrative status) -- no quality/price fabricated."""
    params = {
        "code_postal": code_postal,
        "activite_principale": code_naf,
        "etat_administratif": "A",  # actives uniquement
        "per_page": limite,
    }
    response = requests.get(API_RECHERCHE_ENTREPRISES, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("results", [])


def _enrichir_lien_entreprise(entreprise: dict[str, Any]) -> None:
    """Enrichit une entreprise avec un lien 'lien_fiche_officielle' qui priorise
    le site internet si disponible, sinon utilise l'annuaire gouvernemental."""
    site = entreprise.get("site_internet")
    if site and site.strip():
        # Priorite au site internet de l'entreprise
        entreprise["lien_fiche_officielle"] = site
    else:
        # Fallback sur l'annuaire gouvernemental si pas de site internet
        siren = entreprise.get("siren")
        if siren:
            entreprise["lien_fiche_officielle"] = f"https://annuaire-entreprises.data.gouv.fr/entreprise/{siren}"
        else:
            entreprise["lien_fiche_officielle"] = None


def formater_resultats_non_rge(entreprises_brutes: list[dict[str, Any]], code_postal_cible: str) -> list[dict[str, Any]]:
    """Format raw 'Recherche d'Entreprises' records into the same shape
    used for RGE results, with an objective (not quality) score."""
    resultats = []
    for e in entreprises_brutes:
        siege = e.get("siege", {}) or {}
        score = 0
        details = []

        if e.get("etat_administratif") == "A":
            score += 50
            details.append("Entreprise active au Registre National (+50)")
        else:
            details.append("Statut administratif inconnu ou inactif (+0)")

        if siege.get("code_postal") == code_postal_cible:
            score += 30
            details.append("Meme code postal que l'adresse cible (+30)")
        else:
            score += 10
            details.append("Meme departement seulement (+10)")

        if e.get("date_creation"):
            try:
                anciennete_annees = date.today().year - int(str(e["date_creation"])[:4])
                if anciennete_annees >= 3:
                    score += 20
                    details.append(f"Entreprise creee depuis {anciennete_annees} ans (+20)")
                else:
                    details.append(f"Entreprise recente ({anciennete_annees} an(s)) -- a verifier (+0)")
            except (ValueError, TypeError):
                pass

        entreprise = {
            "nom_entreprise": e.get("nom_complet"),
            "siren": e.get("siren"),
            "adresse": siege.get("adresse"),
            "code_postal": siege.get("code_postal"),
            "commune": siege.get("libelle_commune"),
            "activite_principale": e.get("activite_principale"),
            "date_creation": e.get("date_creation"),
            "score_objectif_sur_100": score,
            "details_score": details,
            "site_internet": None,  # non fourni par cette API -- a rechercher manuellement
        }
        _enrichir_lien_entreprise(entreprise)
        resultats.append(entreprise)

    resultats.sort(key=lambda r: r["score_objectif_sur_100"], reverse=True)
    return resultats


def _extraire_priorite(recommandation: dict[str, Any]) -> str:
    """Tente d'extraire une priorité depuis le JSON source.
    Si elle n'est pas fournie, on retourne un libellé explicite au lieu d'un None."""
    for cle in ("priorite", "priorité", "priority", "priorite_recommandation"):
        valeur = recommandation.get(cle)
        if valeur not in (None, ""):
            return str(valeur)

    mesure = str(recommandation.get("mesure_originale") or recommandation.get("mesure") or "").lower()
    if "priorité" in mesure or "en priorite" in mesure or "prioritaire" in mesure:
        return "Priorité identifiée dans le texte"
    if "urgent" in mesure or "immediat" in mesure or "d'abord" in mesure:
        return "À traiter en premier"
    return "Non renseignée (absente du JSON source)"


def traiter_recommandation(
    recommandation: dict[str, Any],
    code_postal: str,
    lat: float | None = None,
    lon: float | None = None,
) -> dict[str, Any]:
    """Route one recommendation to the right matching path (RGE or non-RGE)
    and return a self-contained, traceable result block."""
    cle = recommandation.get("cle")
    priorite = _extraire_priorite(recommandation)

    metadonnees_origine = {
        k: recommandation[k]
        for k in ("zone_origine", "risques_origine", "mesure_originale", "cout_estime")
        if k in recommandation
    }

    if cle in RECOMMANDATION_VERS_DOMAINE_ADEME:
        entreprises = matcher_recommandation(code_postal, cle, lat, lon)
        # Enrichir les liens des entreprises RGE
        for entreprise in entreprises:
            _enrichir_lien_entreprise(entreprise)
        return {
            "cle": cle,
            "categorie": "rge",
            "priorite": priorite,
            "domaine_recherche": RECOMMANDATION_VERS_DOMAINE_ADEME[cle],
            "entreprises": entreprises,
            "annuaire_reference": {
                "organisme": "France Renov' - annuaire officiel RGE",
                "url": "https://france-renov.gouv.fr/annuaires-professionnels",
            },
            **metadonnees_origine,
        }

    if cle in CATEGORIES_NON_RGE:
        config = CATEGORIES_NON_RGE[cle]
        brutes = rechercher_entreprises_non_rge(code_postal, config["code_naf"])
        entreprises = formater_resultats_non_rge(brutes, code_postal)
        return {
            "cle": cle,
            "categorie": "non_rge",
            "priorite": priorite,
            "libelle": config["libelle"],
            "code_naf_recherche": config["code_naf"],
            "entreprises": entreprises,
            "annuaire_reference": config["annuaire_reference"],
            **metadonnees_origine,
        }

    return {
        "cle": cle,
        "categorie": "inconnue",
        "priorite": priorite,
        "erreur": (
            f"Cle '{cle}' non mappee. Cles RGE disponibles : "
            f"{list(RECOMMANDATION_VERS_DOMAINE_ADEME)} -- Cles non-RGE disponibles : "
            f"{list(CATEGORIES_NON_RGE)}"
        ),
        **metadonnees_origine,
    }


def _extraire_code_postal(data: dict[str, Any]) -> str:
    """Accepte plusieurs variantes de nommage courantes pour le code postal,
    pour eviter un KeyError si le fichier JSON ne suit pas exactement le
    format attendu. En dernier recours, extrait le code postal directement
    depuis une chaine d'adresse complete (ex: '8 Allee du Port Maillard,
    44000 Nantes') via une recherche de 5 chiffres consecutifs -- format
    standard des codes postaux francais."""
    candidats_cles_racine = ["code_postal", "codePostal", "cp", "postal_code"]
    for cle in candidats_cles_racine:
        if cle in data and data[cle]:
            return str(data[cle])

    adresse = data.get("adresse")

    # Cas ou le code postal est niche dans un sous-objet "adresse"
    if isinstance(adresse, dict):
        for cle in candidats_cles_racine:
            if cle in adresse and adresse[cle]:
                return str(adresse[cle])
        # Le sous-objet peut lui-meme contenir un champ texte libre
        adresse = adresse.get("adresse") or adresse.get("label") or adresse.get("adresseLabel")

    # Dernier recours : extraction par regex depuis une adresse texte complete
    if isinstance(adresse, str):
        match = re.search(r"\b\d{5}\b", adresse)
        if match:
            return match.group(0)

    raise KeyError(
        "Impossible de trouver ou d'extraire le code postal. "
        f"Cles presentes a la racine : {list(data.keys())}. "
        "Le fichier doit contenir 'code_postal' (racine ou sous-objet 'adresse'), "
        "ou une adresse texte contenant un code postal a 5 chiffres."
    )


def _extraire_recommandations(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Accepte plusieurs variantes de nommage/structure pour la liste des
    recommandations :
      1. Une liste plate a la racine ('recommandations', 'actions', ...)
      2. Une structure par zones (format resultat_enrichi.json) : chaque
         zone contient 'zone', 'risques' et sa propre liste 'recommandations'
         en texte libre -- dans ce cas, chaque recommandation est classifiee
         automatiquement vers une cle connue via classifier_recommandation().
    """
    candidats_cles = ["recommandations", "recommendations", "actions", "preconisations", "recos"]

    # Cas 1 : liste plate deja au bon format (avec 'cle')
    for cle in candidats_cles:
        valeur = data.get(cle)
        if isinstance(valeur, list) and valeur and "cle" in valeur[0]:
            return valeur

    # Cas 2 : structure par zones (resultat_enrichi.json)
    zones = data.get("zones")
    if isinstance(zones, list) and zones:
        return _extraire_recommandations_depuis_zones(zones)

    print(
        "\nATTENTION : aucune recommandation trouvee ni classifiable. "
        f"Cles presentes a la racine du JSON : {list(data.keys())}"
    )
    return []


def _extraire_recommandations_depuis_zones(zones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aplatit zones[].recommandations et classifie chaque mesure en texte
    libre vers une cle connue (RGE ou non-RGE), a partir de la zone, des
    risques associes et de mots-cles dans le texte de la mesure."""
    resultats: list[dict[str, Any]] = []
    non_classifiees = 0

    for zone_bloc in zones:
        zone = str(zone_bloc.get("zone", "")).lower()
        risques = [str(r).lower() for r in zone_bloc.get("risques", [])]

        for reco in zone_bloc.get("recommandations", []):
            mesure = str(reco.get("mesure", ""))
            cle = _classifier_recommandation(zone, risques, mesure)

            if cle is None:
                non_classifiees += 1
                continue

            resultats.append(
                {
                    "cle": cle,
                    "priorite": reco.get("priorite") or reco.get("priority") or reco.get("priorité") or None,
                    "zone_origine": zone,
                    "risques_origine": risques,
                    "mesure_originale": mesure,
                    "cout_estime": reco.get("cout_estime"),
                }
            )

    if non_classifiees:
        print(f"  ({non_classifiees} mesure(s) non classifiable(s) automatiquement, ignoree(s) -- a traiter manuellement)")

    return resultats


def _classifier_recommandation(zone: str, risques: list[str], mesure: str) -> str | None:
    """Classifie une recommandation en texte libre vers une cle connue
    (RECOMMANDATION_VERS_DOMAINE_ADEME ou CATEGORIES_NON_RGE), a partir de
    regles zone > risques > mots-cles du texte. Retourne None si aucune
    regle ne correspond -- mieux vaut ignorer que mal classifier."""
    mesure_norm = mesure.lower()

    # Priorite 1 : le risque associe a la zone est souvent le signal le plus fiable
    if any("argile" in r or "retrait_gonflement" in r or "mouvement_terrain" in r for r in risques):
        return "rga_geotechnique"
    if any("seisme" in r or "sismique" in r for r in risques):
        return "sismique_structure"
    if any("radon" in r for r in risques):
        return "radon_etancheite"
    if any("inondation" in r or "ruissellement" in r or "submersion" in r for r in risques):
        return "ruissellement_drainage"

    # Priorite 2 : mots-cles explicites dans le texte de la mesure
    if "isoler" in mesure_norm or "isolation" in mesure_norm:
        if "toit" in mesure_norm or "combles" in mesure_norm or zone == "toiture":
            return "isolation_combles"
        if "mur" in mesure_norm or "façade" in mesure_norm or "facade" in mesure_norm or zone == "facade":
            return "isolation_murs_exterieur"
    if "ventilation" in mesure_norm or "étanchéité à l'air" in mesure_norm or "etancheite a l'air" in mesure_norm:
        return "ventilation"
    if "fenêtre" in mesure_norm or "menuiserie" in mesure_norm or "volet" in mesure_norm:
        return "menuiseries"
    if "architecte" in mesure_norm or "maître d'œuvre" in mesure_norm or "audit" in mesure_norm:
        return "audit_energetique"

    # Priorite 3 : zone seule, en dernier recours pour les cas de maintenance
    # generique (couverture, soudures, fixations...) non couverts par un
    # domaine RGE ou un annuaire specifique -- pas de cle fiable disponible.
    return None


def generer_rapport(chemin_json: Path) -> dict[str, Any]:
    data = json.loads(chemin_json.read_text(encoding="utf-8"))
    code_postal = _extraire_code_postal(data)
    recommandations = _extraire_recommandations(data)

    print(f"Adresse : {data.get('adresse', 'N/A')} ({code_postal})")
    print(f"{len(recommandations)} recommandation(s) a traiter.\n")

    resultats = []
    for reco in recommandations:
        print(f"-> {reco.get('cle')} (priorite {reco.get('priorite')})...")
        resultat = traiter_recommandation(reco, code_postal)
        nb = len(resultat.get("entreprises", []))
        print(f"   {nb} entreprise(s) / reference(s) trouvee(s).")
        resultats.append(resultat)

    return {
        "adresse": data.get("adresse"),
        "code_postal": code_postal,
        "recommandations_traitees": resultats,
    }


def creer_html_rapport(rapport: dict[str, Any], chemin_html: Path) -> Path:
    """Genere une version HTML professionnelle du rapport, autonome et lisible."""
    recommandations = rapport.get("recommandations_traitees", [])
    total_recommandations = len(recommandations)
    total_entreprises = sum(len(item.get("entreprises", [])) for item in recommandations)
    categories = Counter(item.get("categorie", "inconnue") for item in recommandations)

    sections_html = []
    for item in recommandations:
        entreprises = item.get("entreprises", [])
        annuaire = item.get("annuaire_reference", {}) or {}
        titre = item.get("libelle") or item.get("domaine_recherche") or item.get("cle") or "Recommandation"
        categorie_label = "RGE" if item.get("categorie") == "rge" else "Non-RGE"
        badge_class = "badge-rge" if item.get("categorie") == "rge" else "badge-non-rge"

        lignes_entreprises = []
        for entreprise in entreprises:
            score = entreprise.get("score_objectif_sur_100", "N/A")
            adresse = entreprise.get("adresse") or "Adresse non communiquee"
            code_postal = entreprise.get("code_postal") or ""
            commune = entreprise.get("commune") or ""
            site = entreprise.get("site_internet") or entreprise.get("lien_fiche_officielle") or ""
            telephone = entreprise.get("telephone") or ""
            email = entreprise.get("email") or ""
            site_html = f'<a href="{html.escape(site, quote=True)}" target="_blank" rel="noopener">Voir le site</a>' if site else "—"

            if telephone and email:
                contact_text = f"{telephone}<br>{email}"
            elif telephone:
                contact_text = telephone
            elif email:
                contact_text = email
            else:
                contact_text = "Contact non disponible dans la source ouverte"

            lignes_entreprises.append(
                f"<tr>"
                f"<td>{html.escape(str(entreprise.get('nom_entreprise') or '—'))}</td>"
                f"<td><strong>{score}</strong>/100</td>"
                f"<td>{html.escape(str(adresse))}<br>{html.escape(f'{code_postal} {commune}'.strip())}</td>"
                f"<td>{html.escape(contact_text)}</td>"
                f"<td>{site_html}</td>"
                f"</tr>"
            )

        entreprises_table = (
            "<table>"
            "<thead><tr><th>Entreprise</th><th>Score</th><th>Adresse</th><th>Contact</th><th>Site officiel</th></tr></thead>"
            f"<tbody>{''.join(lignes_entreprises)}</tbody>"
            "</table>"
        ) if lignes_entreprises else "<p class='empty'>Aucune entreprise n’a été identifiée pour cette recommandation.</p>"

        annuaire_html = ""
        if annuaire:
            url = annuaire.get("url") or ""
            organisme = annuaire.get("organisme") or ""
            note = annuaire.get("note") or ""
            annuaire_html = (
                "<div class='annuaire'>"
                f"<strong>Annuaire de référence :</strong> {html.escape(organisme)}<br>"
                f"<a href='{html.escape(url, quote=True)}' target='_blank' rel='noopener'>{html.escape(url)}</a><br>"
                f"<span>{html.escape(note)}</span>"
                "</div>"
            )

        sections_html.append(
            f"<article class='card'>"
            f"<div class='card-header'><h3>{html.escape(titre)}</h3><span class='badge {badge_class}'>{html.escape(categorie_label)}</span></div>"
            f"<p><strong>Clé :</strong> {html.escape(str(item.get('cle') or '—'))} • <strong>Priorité :</strong> {html.escape(str(item.get('priorite') or 'Non renseignée'))}</p>"
            f"{annuaire_html}"
            f"{entreprises_table}"
            f"</article>"
        )

    summary_cards = []
    summary_cards.append(f"<div class='summary-card'><span>{total_recommandations}</span><small>Recommandations traitées</small></div>")
    summary_cards.append(f"<div class='summary-card'><span>{total_entreprises}</span><small>Entreprises proposées</small></div>")
    summary_cards.append(f"<div class='summary-card'><span>{categories.get('rge', 0)}</span><small>Recommandations RGE</small></div>")
    summary_cards.append(f"<div class='summary-card'><span>{categories.get('non_rge', 0)}</span><small>Recommandations non-RGE</small></div>")

    html_content = f"""<!DOCTYPE html>
<html lang='fr'>
<head>
  <meta charset='utf-8'>
  <meta name='viewport' content='width=device-width, initial-scale=1'>
  <title>Rapport artisans - Vue professionnelle</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f7fb;
      --card: #ffffff;
      --text: #12304a;
      --muted: #5e7385;
      --accent: #1f6feb;
      --accent-2: #0f4c81;
      --border: #dfe8f1;
      --success: #2f9e44;
      --warning: #f59f00;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: 'Segoe UI', Roboto, Arial, sans-serif; background: var(--bg); color: var(--text); }}
    .page {{ max-width: 1280px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{ background: linear-gradient(135deg, var(--accent-2), var(--accent)); color: white; border-radius: 24px; padding: 28px 30px; box-shadow: 0 12px 30px rgba(15, 76, 129, 0.2); }}
    .hero h1 {{ margin: 0 0 8px; font-size: 2rem; }}
    .hero p {{ margin: 0; opacity: 0.95; }}
    .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 16px; margin: 24px 0; }}
    .summary-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 16px; padding: 20px; box-shadow: 0 8px 20px rgba(18, 48, 74, 0.05); }}
    .summary-card span {{ display: block; font-size: 1.6rem; font-weight: 700; color: var(--accent-2); }}
    .summary-card small {{ color: var(--muted); }}
    .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 18px; padding: 20px; margin-bottom: 18px; box-shadow: 0 8px 20px rgba(18, 48, 74, 0.05); }}
    .card-header {{ display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 8px; }}
    .card h3 {{ margin: 0; font-size: 1.1rem; }}
    .badge {{ padding: 6px 10px; border-radius: 999px; font-size: 0.8rem; font-weight: 600; }}
    .badge-rge {{ background: #eaf7ee; color: var(--success); }}
    .badge-non-rge {{ background: #fff6e6; color: var(--warning); }}
    .annuaire {{ margin: 10px 0 16px; padding: 12px 14px; border-left: 4px solid var(--accent); background: #f7faff; border-radius: 10px; color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; margin-top: 8px; }}
    th, td {{ padding: 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }}
    th {{ background: #f8fbff; color: var(--muted); font-size: 0.9rem; text-transform: uppercase; letter-spacing: 0.04em; }}
    tr:hover {{ background: #fbfdff; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .empty {{ color: var(--muted); font-style: italic; }}
    .company-meta {{ margin-top: 10px; padding: 10px 12px; border: 1px solid var(--border); border-radius: 10px; background: #fbfdff; }}
    .company-meta summary {{ cursor: pointer; font-weight: 600; color: var(--accent-2); }}
    .company-meta ul {{ margin: 8px 0 0 18px; padding: 0; }}
    .company-meta li {{ margin-bottom: 6px; color: var(--muted); }}
    @media (max-width: 700px) {{
      .page {{ padding: 16px 12px 36px; }}
      table {{ display: block; overflow-x: auto; }}
    }}
  </style>
</head>
<body>
  <div class='page'>
    <section class='hero'>
      <h1>Rapport artisans — Vue professionnelle</h1>
      <p>Adresse : {html.escape(str(rapport.get('adresse') or 'Non renseignée'))} · Code postal : {html.escape(str(rapport.get('code_postal') or 'N/A'))}</p>
    </section>
    <section class='summary'>{''.join(summary_cards)}</section>
    <section>{''.join(sections_html)}</section>
  </div>
</body>
</html>
"""
    chemin_html.write_text(html_content, encoding="utf-8")
    return chemin_html


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Genere les matchs artisans + liens partenaires pour toutes les recommandations d'un rapport"
    )
    parser.add_argument("--json", required=True, type=Path, help="Fichier JSON des recommandations")
    parser.add_argument("--output", type=Path, default=Path("rapport_artisans_matches.json"))
    args = parser.parse_args()

    rapport = generer_rapport(args.json)
    args.output.write_text(json.dumps(rapport, ensure_ascii=False, indent=2), encoding="utf-8")
    html_output = args.output.with_suffix('.html')
    creer_html_rapport(rapport, html_output)
    print(f"\nTermine. Rapport JSON : {args.output}")
    print(f"Rapport HTML : {html_output}")
