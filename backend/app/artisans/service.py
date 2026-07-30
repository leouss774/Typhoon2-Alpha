"""Matching d'entreprises réelles via les données ouvertes françaises."""

from __future__ import annotations

import re
from datetime import date
from typing import Any
from urllib.parse import urlparse

import httpx

from app.artisans.classification import classer_avec_mistral, decision_regle
from app.artisans.site_finder import enrichir_coordonnees

ADEME_API = "https://data.ademe.fr/data-fair/api/v1/datasets/liste-des-entreprises-rge-2/lines"
ENTREPRISES_API = "https://recherche-entreprises.api.gouv.fr/search"

ANNUAIRE_HOSTS = {
    "annuaire-entreprises.data.gouv.fr",
    "data.ademe.fr",
    "france-renov.gouv.fr",
}

RGE_DOMAINES = {
    "isolation_combles": "Isolation des combles perdus",
    "isolation_toiture": "Isolation des toitures terrasses ou des toitures par l'extérieur",
    "isolation_murs_interieur": "Isolation par l'intérieur des murs ou rampants de toitures  ou plafonds",
    "isolation_murs_exterieur": "Isolation des murs par l'extérieur",
    "ventilation": "Ventilation mécanique",
    "audit_energetique": "Audit énergétique Maison individuelle",
    "menuiseries": "Fenêtres, volets, portes donnant sur l'extérieur",
}

NON_RGE = {
    "travaux_facade": {
        "libelle": "Travaux de façade et de maçonnerie",
        "code_naf": "43.31Z",
        "annuaire_reference": {
            "organisme": "Annuaire des entreprises — service public",
            "url": "https://annuaire-entreprises.data.gouv.fr/",
        },
    },
    "travaux_toiture": {
        "libelle": "Travaux de couverture et de toiture",
        "code_naf": "43.91B",
        "annuaire_reference": {
            "organisme": "Annuaire des entreprises — service public",
            "url": "https://annuaire-entreprises.data.gouv.fr/",
        },
    },
    "travaux_fondations": {
        "libelle": "Travaux de fondations et maçonnerie spécialisée",
        "code_naf": "43.99C",
        "annuaire_reference": {
            "organisme": "Annuaire des entreprises — service public",
            "url": "https://annuaire-entreprises.data.gouv.fr/",
        },
    },
    "rga_geotechnique": {
        "libelle": "Étude et confortement géotechnique (RGA)", "code_naf": "71.12B",
        "annuaire_reference": {"organisme": "Union Syndicale Géotechnique", "url": "https://www.usg.asso.fr/annuaire-des-membres/"},
    },
    "sismique_structure": {
        "libelle": "Diagnostic et renforcement parasismique", "code_naf": "71.12B",
        "annuaire_reference": {"organisme": "CINOV Construction", "url": "https://www.cinov.fr/annuaire-cinov/"},
    },
    "radon_etancheite": {
        "libelle": "Étanchéité et ventilation anti-radon", "code_naf": "43.99C",
        "annuaire_reference": {"organisme": "ASNR — ressources radon", "url": "https://www.asnr.fr/"},
    },
    "ruissellement_drainage": {
        "libelle": "Drainage et gestion du ruissellement pluvial", "code_naf": "43.99C",
        "annuaire_reference": {"organisme": "CEPRI — guides méthodologiques", "url": "https://cepri.net/"},
    },
}


def extraire_code_postal(adresse: str) -> str:
    match = re.search(r"\b(?:0[1-9]|[1-8]\d|9[0-8])\d{3}\b", adresse or "")
    if not match:
        raise ValueError("L'adresse doit contenir un code postal français à 5 chiffres.")
    return match.group(0)


def classifier_recommandation(zone: str, risques: list[str], mesure: str) -> str | None:
    zone_norm, texte = (zone or "").lower(), (mesure or "").lower()
    contexte = f"{zone_norm} {' '.join(risques).lower()} {texte}"
    if any(x in contexte for x in ("retrait_gonflement", "retrait-gonflement", "argile", "rga")):
        return "rga_geotechnique"
    if any(x in contexte for x in ("séisme", "seisme", "sismique", "parasism")):
        return "sismique_structure"
    if "radon" in contexte:
        return "radon_etancheite"
    if any(x in contexte for x in ("inondation", "ruissellement", "submersion", "drainage", "remontée de nappe")):
        return "ruissellement_drainage"
    if any(x in texte for x in ("fenêtre", "fenetre", "menuiserie", "volet", "porte extérieure")):
        return "menuiseries"
    if any(x in texte for x in ("ventilation", "vmc", "étanchéité à l'air", "etancheite a l'air")):
        return "ventilation"
    if any(x in texte for x in ("audit énergétique", "audit energetique", "architecte", "maître d'œuvre", "maitre d'oeuvre")):
        return "audit_energetique"
    if any(x in texte for x in ("isolation", "isoler")):
        if any(x in contexte for x in ("toit", "toiture", "comble")):
            return "isolation_combles"
        if any(x in contexte for x in ("mur", "façade", "facade")):
            return "isolation_murs_exterieur"
    # Repli par élément du bâtiment : une recommandation RAG peut rester
    # générique ("respecter les techniques locales de façade") tout en
    # désignant clairement le corps de métier à rechercher.
    if any(x in zone_norm for x in ("mur", "façade", "facade")):
        return "travaux_facade"
    if any(x in zone_norm for x in ("toit", "toiture", "comble")):
        return "travaux_toiture"
    if any(x in zone_norm for x in ("fondation", "sous_sol", "sous-sol")):
        return "travaux_fondations"
    return None


def _date_valide(value: Any) -> bool:
    try:
        return bool(value) and date.fromisoformat(str(value)[:10]) >= date.today()
    except ValueError:
        return False


def _site_officiel(value: Any) -> str | None:
    """Retourne un site d'entreprise, jamais une fiche d'annuaire public."""
    raw = str(value or "").strip()
    if not raw:
        return None
    url = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host or "." not in host or host in ANNUAIRE_HOSTS:
        return None
    return url


def _score_rge(e: dict[str, Any], code_postal: str) -> dict[str, Any]:
    valide = _date_valide(e.get("lien_date_fin"))
    meme_cp = str(e.get("code_postal") or "") == code_postal
    contact = bool(e.get("telephone") or e.get("email"))
    site_officiel = _site_officiel(e.get("site_internet"))
    return {
        **e,
        "site_officiel": site_officiel,
        "score_objectif_sur_100": (50 if valide else 0) + (30 if meme_cp else 10) + (20 if contact else 0),
        "qualification_valide": valide,
        "details_score": [
            "Qualification RGE valide (+50)" if valide else "Qualification expirée ou date inconnue (+0)",
            "Même code postal (+30)" if meme_cp else "Même département (+10)",
            "Contact disponible (+20)" if contact else "Contact absent des données ouvertes (+0)",
        ],
        "type_lien": "site_entreprise" if site_officiel else None,
    }


async def rechercher_rge(client: httpx.AsyncClient, code_postal: str, domaine: str, limite: int) -> list[dict[str, Any]]:
    params = {
        "qs": f'code_postal:"{code_postal}" AND domaine:"{domaine}"', "size": limite,
        "select": "siret,nom_entreprise,adresse,code_postal,commune,telephone,email,site_internet,domaine,organisme,lien_date_debut,lien_date_fin,latitude,longitude",
    }
    response = await client.get(ADEME_API, params=params)
    response.raise_for_status()
    records = response.json().get("results", [])
    if not records:
        params["qs"] = f'code_postal:{code_postal[:2]}* AND domaine:"{domaine}"'
        response = await client.get(ADEME_API, params=params)
        response.raise_for_status()
        records = response.json().get("results", [])
    return sorted((_score_rge(e, code_postal) for e in records), key=lambda e: e["score_objectif_sur_100"], reverse=True)


def _formater_non_rge(e: dict[str, Any], code_postal: str) -> dict[str, Any]:
    siege, siren = e.get("siege") or {}, e.get("siren")
    meme_cp, active = str(siege.get("code_postal") or "") == code_postal, e.get("etat_administratif") == "A"
    try:
        anciennete = date.today().year - int(str(e.get("date_creation"))[:4])
    except (TypeError, ValueError):
        anciennete = 0
    return {
        "nom_entreprise": e.get("nom_complet"), "siren": siren, "adresse": siege.get("adresse"),
        "code_postal": siege.get("code_postal"), "commune": siege.get("libelle_commune"),
        "activite_principale": e.get("activite_principale"), "date_creation": e.get("date_creation"),
        "site_internet": None,
        "site_officiel": None,
        "score_objectif_sur_100": (50 if active else 0) + (30 if meme_cp else 10) + (20 if anciennete >= 3 else 0),
        "details_score": [
            "Entreprise active au Registre national (+50)" if active else "Entreprise inactive ou statut inconnu (+0)",
            "Même code postal (+30)" if meme_cp else "Même département (+10)",
            f"Entreprise créée depuis {anciennete} ans (+20)" if anciennete >= 3 else "Ancienneté inférieure à 3 ans ou inconnue (+0)",
        ],
        "type_lien": None,
    }


async def rechercher_non_rge(client: httpx.AsyncClient, code_postal: str, code_naf: str, limite: int) -> list[dict[str, Any]]:
    response = await client.get(ENTREPRISES_API, params={
        "code_postal": code_postal, "activite_principale": code_naf,
        "etat_administratif": "A", "per_page": limite,
    })
    response.raise_for_status()
    return sorted(
        (_formater_non_rge(e, code_postal) for e in response.json().get("results", [])),
        key=lambda e: e["score_objectif_sur_100"], reverse=True,
    )


async def matcher(adresse: str, zones: list[dict[str, Any]], limite: int = 5, client: httpx.AsyncClient | None = None) -> dict[str, Any]:
    code_postal, groupes, non_classifiees = extraire_code_postal(adresse), {}, 0
    journal_classification: list[dict[str, Any]] = []
    for zone in zones:
        risques = [str(r) for r in zone.get("risques", [])]
        for reco in zone.get("recommandations", []):
            mesure = str(reco.get("mesure") or reco.get("travaux") or "")
            zone_name = str(zone.get("zone", ""))
            categorie_regle = classifier_recommandation(zone_name, risques, mesure)
            decision = (
                decision_regle(categorie_regle)
                if categorie_regle
                else await classer_avec_mistral(zone_name, risques, mesure)
            )
            cle = decision.categorie
            journal_classification.append({
                "zone": zone_name,
                "mesure": mesure,
                **decision.to_dict(),
            })
            if not cle:
                non_classifiees += 1
                continue
            groupe = groupes.setdefault(cle, {"cle": cle, "mesures": [], "classifications": []})
            if mesure and mesure not in groupe["mesures"]:
                groupe["mesures"].append(mesure)
            groupe["classifications"].append(decision.to_dict())

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=15, follow_redirects=True)
    try:
        resultats = []
        for cle, groupe in groupes.items():
            try:
                if cle in RGE_DOMAINES:
                    groupe.update(categorie="rge", domaine_recherche=RGE_DOMAINES[cle],
                        annuaire_reference={"organisme": "France Rénov' — annuaire officiel RGE", "url": "https://france-renov.gouv.fr/annuaires-professionnels"},
                        entreprises=await rechercher_rge(client, code_postal, RGE_DOMAINES[cle], limite))
                else:
                    config = NON_RGE[cle]
                    groupe.update(categorie="non_rge", libelle=config["libelle"],
                        annuaire_reference=config["annuaire_reference"],
                        entreprises=await rechercher_non_rge(client, code_postal, config["code_naf"], limite))
                for entreprise in groupe["entreprises"]:
                    if not all(entreprise.get(key) for key in ("site_officiel", "telephone", "email")):
                        contact = await enrichir_coordonnees(entreprise)
                        for key in ("site_officiel", "telephone", "email"):
                            if not entreprise.get(key) and contact.get(key):
                                entreprise[key] = contact[key]
                        if contact.get("site_officiel"):
                            entreprise["type_lien"] = "site_entreprise_mistral_web_search"
                        if any(contact.values()):
                            entreprise["contact_enrichi_par"] = "mistral_web_search"
            except (httpx.HTTPError, ValueError) as exc:
                groupe.update(entreprises=[], erreur=f"Source externe indisponible : {type(exc).__name__}")
            resultats.append(groupe)
    finally:
        if owns_client:
            await client.aclose()
    return {
        "adresse": adresse, "code_postal": code_postal,
        "avertissement_score": "Score objectif de correspondance, pas une note de qualité/prix.",
        "avertissement_sites": (
            "Sites issus des donnees publiques ou recherches par Mistral Web Search. "
            "Aucun lien n'est affiche lorsque le site officiel ne peut pas etre confirme."
        ),
        "recommandations_traitees": resultats,
        "recommandations_non_classifiees": non_classifiees,
        "journal_classification": journal_classification,
    }
