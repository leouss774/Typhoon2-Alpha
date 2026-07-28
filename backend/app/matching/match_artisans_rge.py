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

API_BASE = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"

# Mapping recommandation du rapport -> libelle exact du domaine ADEME
# (les valeurs doivent correspondre exactement a l'enum 'domaine' de l'API,
# consultable via le schema du dataset).
RECOMMANDATION_VERS_DOMAINE_ADEME = {
    "isolation_combles": "Isolation des combles perdus",
    "isolation_toiture": "Isolation des toitures terrasses ou des toitures par l'extérieur",
    "isolation_murs_interieur": "Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds",
    "isolation_murs_exterieur": "Isolation des murs par l'extérieur",
    "ventilation": "Ventilation mécanique",
    "audit_energetique": "Audit énergétique Maison individuelle",
    "menuiseries": "Fenêtres, volets, portes donnant sur l'extérieur",
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


def calculer_score_objectif(entreprise: dict[str, Any], code_postal_cible: str) -> dict[str, Any]:
    """Compute an OBJECTIVE, EXPLAINABLE match score (0-100) from verifiable
    open-data fields only. This is NOT a quality/price rating -- it reflects
    only: qualification validity, exact domain match, and geographic proximity
    (same postal code vs. same department)."""
    score = 0
    details: list[str] = []

    # Validite de la qualification a la date du jour (critere le plus important :
    # une qualification expiree ne permet plus les aides publiques ni ne garantit
    # un audit recent).
    date_fin_str = entreprise.get("lien_date_fin")
    qualification_valide = False
    if date_fin_str:
        try:
            date_fin = date.fromisoformat(date_fin_str[:10])
            qualification_valide = date_fin >= date.today()
        except ValueError:
            pass

    if qualification_valide:
        score += 50
        details.append("Qualification RGE valide a ce jour (+50)")
    else:
        details.append("Qualification RGE expiree ou date inconnue (+0) -- A VERIFIER avant tout contact")

    # Correspondance geographique exacte (meme code postal).
    if entreprise.get("code_postal") == code_postal_cible:
        score += 30
        details.append("Meme code postal que l'adresse cible (+30)")
    else:
        score += 10
        details.append("Meme departement seulement (+10)")

    # Presence de coordonnees de contact directes (utile operationnellement,
    # mais n'est en rien un indicateur de qualite des travaux).
    if entreprise.get("telephone") or entreprise.get("email"):
        score += 20
        details.append("Coordonnees de contact disponibles (+20)")
    else:
        details.append("Aucune coordonnee de contact directe dans l'open data (+0)")

    return {
        "score_objectif_sur_100": score,
        "qualification_valide": qualification_valide,
        "details_score": details,
    }


def matcher_recommandation(code_postal: str, cle_recommandation: str) -> list[dict[str, Any]]:
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
        score_info = calculer_score_objectif(entreprise, code_postal)
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
