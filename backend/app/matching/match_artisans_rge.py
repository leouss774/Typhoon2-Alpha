# -*- coding: utf-8 -*-
"""
match_artisans_rge.py
========================
Trouve des entreprises RGE REELLES (donnee ouverte ADEME, licence Etalab)
correspondant a une recommandation de renovation thermique du rapport,
et calcule un score de matching base sur des criteres VERIFIABLES.

IMPORTANT - Ce que ce script ne fait PAS :
- Il n'invente aucune entreprise, aucun avis client, aucun prix.
- Le "score qualite/prix" demande dans le rapport n'existe dans aucune
  base ouverte francaise (pas d'API nationale d'avis clients artisans
  fiable et gratuite) -- fabriquer un tel score serait une donnee
  inventee presentee comme fiable, ce qui est dangereux pour une
  decision d'assurance ou un choix de prestataire.
- A la place, ce script calcule un score OBJECTIF et EXPLICABLE, base
  uniquement sur des criteres verifiables dans la donnee ouverte :
  validite de la qualification, correspondance exacte du domaine,
  distance geographique, anciennete de la qualification.

Pour un vrai score qualite/prix, il faudrait brancher une source tierce
(Google Places ratings, Societeinfo, Pages Jaunes Pro...) -- voir note
en fin de fichier.

Usage :
    python match_artisans_rge.py --code-postal 44000 --domaine "Isolation des combles perdus"
"""

from __future__ import annotations

import argparse
import math
from datetime import date
from typing import Any

import requests

from app.matching.cache import rge_cache

API_BASE = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"

# Rayon de la Terre en km
_R = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en km entre deux points GPS (formule de Haversine)."""
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return _R * c

# ─────────────────────────────────────────────────────────────
# Mapping recommandation -> libelle exact du domaine ADEME
# Les valeurs doivent correspondre exactement a l'enum 'domaine'
# de l'API (consultable via le schema du dataset).
# ─────────────────────────────────────────────────────────────
RECOMMANDATION_VERS_DOMAINE_ADEME: dict[str, str] = {
    # Isolation
    "isolation_combles": "Isolation des combles perdus",
    "isolation_toiture": "Isolation des toitures terrasses ou des toitures par l'extérieur",
    "isolation_murs_interieur": "Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds",
    "isolation_murs_exterieur": "Isolation des murs par l'extérieur",
    "isolation_plancher": "Isolation des planchers bas",
    # Chauffage et ECS
    "chauffage_pac": "Chauffage et production d'eau chaude",
    "chauffage_bois": "Chauffage et production d'eau chaude",
    "chauffe_eau_solaire": "Chauffe-eau solaire",
    "chauffe_eau_thermo": "Chauffe-eau thermodynamique",
    # EnR / Electricité
    "panneaux_solaires": "Panneaux solaires photovoltaïques",
    "panneaux_hybrides": "Panneaux solaires hybrides",
    # Ventilation
    "ventilation": "Ventilation mécanique",
    "ventilation_double_flux": "Ventilation mécanique",
    # Audit & Menuiseries
    "audit_energetique": "Audit énergétique Maison individuelle",
    "menuiseries": "Fenêtres, volets, portes donnant sur l'extérieur",
    "porte_isolee": "Fenêtres, volets, portes donnant sur l'extérieur",
}


def rechercher_entreprises_rge(
    code_postal: str,
    domaine: str,
    limite: int = 20,
) -> list[dict[str, Any]]:
    """Query the real ADEME open data API for RGE companies matching a
    postal code and a work domain. Returns raw records, no fabrication."""
    params = {
        "qs": f'code_postal:"{code_postal}" AND domaine:"{domaine}"',
        "size": limite,
        "select": (
            "siret,nom_entreprise,adresse,code_postal,commune,telephone,"
            "email,site_internet,domaine,organisme,lien_date_debut,lien_date_fin,latitude,longitude"
        ),
    }
    response = requests.get(API_BASE, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("results", [])


def rechercher_entreprises_rge_zone_elargie(
    code_postal_prefix: str,
    domaine: str,
    limite: int = 20,
) -> list[dict[str, Any]]:
    """Fallback: widen the search to the department (first 2 digits of
    postal code) if the exact commune has too few results."""
    params = {
        "qs": f'code_postal:{code_postal_prefix}* AND domaine:"{domaine}"',
        "size": limite,
    }
    response = requests.get(API_BASE, params=params, timeout=30)
    response.raise_for_status()
    return response.json().get("results", [])


def _anciennete_ans(date_str: str | None) -> int | None:
    """Calcule le nombre d'années depuis une date ISO."""
    if not date_str:
        return None
    try:
        d = date.fromisoformat(date_str[:10])
        return date.today().year - d.year
    except (ValueError, IndexError):
        return None


def calculer_score_objectif(
    entreprise: dict[str, Any],
    code_postal_cible: str,
    lat_cible: float | None = None,
    lon_cible: float | None = None,
) -> dict[str, Any]:
    """Compute an OBJECTIVE, EXPLAINABLE match score (0-100) from verifiable
    open-data fields only.

    Critères (poids) — max 100 points :
      - Validité qualification RGE      (+40)
      - Ancienneté de la qualification  (+10 max)  # NOUVEAU
      - Proximité géographique          (+25 max)
      - Coordonnées de contact          (+15)
      - Site internet                   (+10)       # NOUVEAU

    Si lat_cible/lon_cible sont fournis, le score géographique utilise la
    distance Haversine réelle au lieu du seul code postal.
    """
    score = 0
    details: list[str] = []

    # --- 1. Validite de la qualification (poids fort) ---
    date_fin_str = entreprise.get("lien_date_fin")
    qualification_valide = False
    if date_fin_str:
        try:
            date_fin = date.fromisoformat(date_fin_str[:10])
            qualification_valide = date_fin >= date.today()
        except ValueError:
            pass

    if qualification_valide:
        score += 40
        details.append("Qualification RGE valide à ce jour (+40)")
    else:
        details.append("Qualification RGE expirée ou date inconnue (+0) — À VÉRIFIER avant tout contact")

    # --- 2. Ancienneté de la qualification RGE (NOUVEAU) ---
    anciennete = _anciennete_ans(entreprise.get("lien_date_debut"))
    if anciennete is not None and qualification_valide:
        if anciennete >= 10:
            pts = 10
            label = f"Certifié RGE depuis {anciennete} ans (+{pts})"
        elif anciennete >= 5:
            pts = 7
            label = f"Certifié RGE depuis {anciennete} ans (+{pts})"
        elif anciennete >= 3:
            pts = 5
            label = f"Certifié RGE depuis {anciennete} ans (+{pts})"
        elif anciennete >= 1:
            pts = 3
            label = f"Certifié RGE depuis {anciennete} an(s) (+{pts})"
        else:
            pts = 0
            label = f"Certification RGE récente ({anciennete} an(s)) (+{pts})"
        score += pts
        details.append(label)
    elif qualification_valide:
        details.append("Ancienneté RGE non déterminée (date début inconnue) (+0)")

    # --- 3. Proximité géographique ---
    # Si on a les coordonnées de la cible ET de l'entreprise, on calcule
    # la distance réelle. Sinon on revient au code postal.
    lat_ent = entreprise.get("latitude")
    lon_ent = entreprise.get("longitude")

    dist_km: float | None = None
    if lat_cible is not None and lon_cible is not None and lat_ent and lon_ent:
        try:
            dist_km = haversine_km(float(lat_cible), float(lon_cible), float(lat_ent), float(lon_ent))
            # Score dégressif avec la distance :
            #   < 5 km  → +25 (même commune)
            #   < 15 km → +20 (commune voisine)
            #   < 30 km → +15 (même bassin)
            #   < 60 km → +10 (même département)
            #   ≥ 60 km → +5  (au-delà)
            if dist_km < 5:
                geoscore = 25
                geolabel = f"Même commune ({dist_km:.1f} km) (+{geoscore})"
            elif dist_km < 15:
                geoscore = 20
                geolabel = f"Commune voisine ({dist_km:.1f} km) (+{geoscore})"
            elif dist_km < 30:
                geoscore = 15
                geolabel = f"Même bassin d'emploi ({dist_km:.1f} km) (+{geoscore})"
            elif dist_km < 60:
                geoscore = 10
                geolabel = f"Même département ({dist_km:.1f} km) (+{geoscore})"
            else:
                geoscore = 5
                geolabel = f"Éloigné ({dist_km:.1f} km) (+{geoscore})"
            score += geoscore
            details.append(geolabel)
        except (ValueError, TypeError):
            # Fallback si les coordonnées sont invalides
            p, d = _score_proximite_cp(entreprise, code_postal_cible)
            score += p
            details.append(d)
    else:
        p, d = _score_proximite_cp(entreprise, code_postal_cible)
        score += p
        details.append(d)

    # --- 4. Coordonnées de contact ---
    tel = entreprise.get("telephone")
    email = entreprise.get("email")
    if tel and email:
        score += 15
        details.append("Téléphone et email disponibles (+15)")
    elif tel or email:
        score += 10
        details.append("Téléphone ou email disponible (+10)")
    else:
        details.append("Aucune coordonnée de contact dans l'open data (+0)")

    # --- 5. Site internet (NOUVEAU) ---
    if entreprise.get("site_internet"):
        score += 10
        details.append("Site internet professionnel disponible (+10)")
    else:
        details.append("Aucun site internet dans l'open data (+0)")

    return {
        "score_objectif_sur_100": min(score, 100),  # clamp au cas où
        "qualification_valide": qualification_valide,
        "details_score": details,
        "distance_km": round(dist_km, 1) if dist_km is not None else None,
        "anciennete_rge_ans": anciennete,
    }


def _score_proximite_cp(
    entreprise: dict[str, Any],
    code_postal_cible: str,
) -> tuple[int, str]:
    """Score de proximité basé sur le code postal (fallback quand pas de coordonnées).
    Retourne (points, description)."""
    if entreprise.get("code_postal") == code_postal_cible:
        return 25, "Même code postal que l'adresse cible (+25)"
    else:
        return 10, "Même département seulement (+10)"


def matcher_recommandation(
    code_postal: str,
    cle_recommandation: str,
    lat: float | None = None,
    lon: float | None = None,
) -> list[dict[str, Any]]:
    """Cherche des entreprises RGE pour une recommandation, avec ou sans coordonnées GPS.

    Si lat/lon sont fournis, le score intègre la distance réelle (Haversine).
    """
    domaine = RECOMMANDATION_VERS_DOMAINE_ADEME.get(cle_recommandation)
    if not domaine:
        raise ValueError(
            f"Recommandation '{cle_recommandation}' non mappee. "
            f"Cles disponibles : {list(RECOMMANDATION_VERS_DOMAINE_ADEME)}"
        )

    resultats = rechercher_entreprises_rge(code_postal, domaine)
    if not resultats:
        print(f"  Aucun resultat sur le code postal exact {code_postal}, elargissement au departement...")
        resultats = rechercher_entreprises_rge_zone_elargie(code_postal[:2], domaine)

    entreprises_scorees = []
    for entreprise in resultats:
        score_info = calculer_score_objectif(entreprise, code_postal, lat, lon)
        entreprises_scorees.append({**entreprise, **score_info})

    entreprises_scorees.sort(key=lambda e: e["score_objectif_sur_100"], reverse=True)
    return entreprises_scorees


def afficher_resultats(entreprises: list[dict[str, Any]]) -> None:
    for e in entreprises:
        print(f"\n  {e.get('nom_entreprise')} (SIRET {e.get('siret')})")
        print(f"    Adresse   : {e.get('adresse')}, {e.get('code_postal')} {e.get('commune')}")
        print(f"    Contact   : {e.get('telephone') or 'N/A'} / {e.get('email') or 'N/A'}")
        print(f"    Domaine   : {e.get('domaine')}")
        print(f"    Score     : {e['score_objectif_sur_100']}/100")
        for d in e["details_score"]:
            print(f"      - {d}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Matching artisans RGE reels (open data ADEME)")
    parser.add_argument("--code-postal", required=True)
    parser.add_argument(
        "--recommandation",
        required=True,
        choices=list(RECOMMANDATION_VERS_DOMAINE_ADEME),
        help="Cle de recommandation issue du rapport (voir RECOMMANDATION_VERS_DOMAINE_ADEME)",
    )
    args = parser.parse_args()

    print(f"Recherche d'entreprises RGE pour '{args.recommandation}' a {args.code_postal}...")
    resultats = matcher_recommandation(args.code_postal, args.recommandation)
    print(f"{len(resultats)} entreprise(s) trouvee(s).")
    afficher_resultats(resultats)

# ─────────────────────────────────────────────────────────────
# NOTE SUR LE SCORE QUALITE/PRIX DEMANDE INITIALEMENT
# ─────────────────────────────────────────────────────────────
# Aucune base ouverte francaise ne fournit de notation qualite/prix
# fiable et gratuite pour les artisans RGE. Pour l'obtenir reellement
# (pas invente), il faudrait brancher UNE des sources suivantes,
# chacune avec ses limites :
#
#   - Google Places API (note moyenne + nombre d'avis) : payant au-dela
#     d'un quota gratuit, necessite une cle API Google Cloud.
#   - Societeinfo / Pages Jaunes Pro : bases commerciales, payantes,
#     donnees SIREN/SIRET enrichies mais pas de note qualite normalisee.
#   - Qualibat (annuaire officiel) : indique le niveau de qualification
#     (ex: 7131 vs 7132) qui EST un proxy de competence technique reconnu
#     par la profession, contrairement a une note d'avis clients.
#
# Recommandation : le score objectif ci-dessus (qualification + zone +
# contact) est deja exploitable pour presenter 3-5 options credibles au
# client assure ; le choix final et la negociation du prix restent de la
# responsabilite du client / du bureau d'etudes, pas de l'agent.
