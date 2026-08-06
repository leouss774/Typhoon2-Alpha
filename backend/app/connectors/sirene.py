"""
Connecteur SIRENE (Système d'Identification du Répertoire des Entreprises).

Interroge l'API SIRENE de l'INSEE pour identifier le type d'activité économique
d'un établissement (code NAF/APE) et confirmer s'il s'agit d'une usine, entrepôt,
bureau, ou autre type de bâtiment.

API : https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/iteminfo.jag?tenantId=insee
Authentification : Nécessite un token OAuth2 (client_id + client_secret)
Documentation : https://api.insee.fr/catalogue/site/themes/wso2/subthemes/insee/pages/iteminfo.jag?tenantId=insee

Note : L'API SIRENE est optionnelle. Si les clés API ne sont pas configurées,
le connecteur retourne un résultat vide sans erreur.
"""

from __future__ import annotations

import httpx
import logging
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Codes NAF/APE correspondant à des activités industrielles
CODES_NAF_INDUSTRIELS = {
    # Industrie manufacturière
    "10": "Industrie alimentaire",
    "11": "Fabrication de boissons",
    "12": "Fabrication de produits du tabac",
    "13": "Fabrication de textiles",
    "14": "Industrie de l'habillement",
    "15": "Industrie du cuir et de la chaussure",
    "16": "Travail du bois et fabrication d'articles en bois",
    "17": "Industrie du papier et du carton",
    "18": "Imprimerie et reproduction d'enregistrements",
    "19": "Cokéfaction et raffinage",
    "20": "Industrie chimique",
    "21": "Industrie pharmaceutique",
    "22": "Fabrication de produits en caoutchouc et en plastique",
    "23": "Fabrication d'autres produits minéraux non métalliques",
    "24": "Métallurgie",
    "25": "Fabrication de produits métalliques",
    "26": "Fabrication de produits informatiques, électroniques et optiques",
    "27": "Fabrication d'équipements électriques",
    "28": "Fabrication de machines et équipements",
    "29": "Industrie automobile",
    "30": "Fabrication d'autres matériels de transport",
    "31": "Fabrication de meubles",
    "32": "Autres industries manufacturières",
    "33": "Réparation et installation de machines et d'équipements",
    # Construction
    "41": "Construction de bâtiments",
    "42": "Génie civil",
    "43": "Travaux de construction spécialisés",
    # Commerce de gros
    "46": "Commerce de gros",
    # Transport et entreposage
    "49": "Transport terrestre et transport par conduites",
    "50": "Transport par eau",
    "51": "Transport aérien",
    "52": "Entreposage et services auxiliaires des transports",
    "53": "Activités de poste et de courrier",
}

# Codes NAF correspondant à des bureaux/commerces
CODES_NAF_BUREAUX = {
    "58": "Édition",
    "59": "Production de films, de programmes de télévision et de programmes audio-visuels",
    "60": "Programmation, diffusion et télédiffusion",
    "61": "Télécommunications",
    "62": "Programmation, conseil et autres activités informatiques",
    "63": "Services d'information",
    "64": "Activités des services financiers",
    "65": "Assurance",
    "66": "Activités auxiliaires de services financiers et d'assurance",
    "69": "Activités juridiques et comptables",
    "70": "Activités des sièges sociaux",
    "71": "Activités d'architecture et d'ingénierie",
    "72": "Recherche-développement scientifique",
    "73": "Publicité et études de marché",
    "74": "Autres activités spécialisées, scientifiques et techniques",
    "75": "Activités vétérinaires",
    "78": "Activités de location et location-bail",
    "79": "Activités des agences de voyage et autres services de réservation",
    "80": "Enquêtes et sécurité",
    "81": "Services relatifs aux bâtiments et aménagement paysager",
    "82": "Activités administratives et autres activités de soutien aux entreprises",
}


async def fetch_sirene(
    client: httpx.AsyncClient,
    siret: str | None = None,
    geo_coords: tuple[float, float] | None = None,
    radius_m: int = 200,
) -> dict[str, Any] | None:
    """
    Interroge l'API SIRENE pour obtenir des informations sur un établissement.

    Parameters
    ----------
    client : httpx.AsyncClient
        Client HTTP asynchrone
    siret : str | None
        Numéro SIRET de l'établissement (si connu)
    geo_coords : tuple[float, float] | None
        Coordonnées (lat, lon) pour recherche géographique
    radius_m : int
        Rayon de recherche en mètres (défaut: 200m)

    Returns
    -------
    dict | None
        {
            "siret": str,
            "naf_code": str,
            "naf_label": str,
            "type_etablissement": "industriel" | "bureaux" | "commercial" | "inconnu",
            "confiance": float (0-1),
            "effectifs": int | None,
            "date_creation": str | None,
            "nom_entreprise": str | None,
            "adresse": str | None,
            "erreur": str | None
        }
    """
    # Vérifier que les clés API sont configurées
    if not settings.insee_client_id or not settings.insee_client_secret:
        logger.info("sirene -- clés API INSEE non configurées, SIRENE désactivé")
        return None

    # Si pas de SIRET ni de coordonnées, on ne peut pas interroger
    if not siret and not geo_coords:
        logger.warning("sirene -- ni SIRET ni coordonnées fournis")
        return None

    try:
        # Étape 1: Obtenir un token OAuth2
        token = await _get_oauth_token(client)
        if not token:
            return {"erreur": "Impossible d'obtenir le token OAuth2"}

        # Étape 2: Rechercher l'établissement
        if siret:
            result = await _search_by_siret(client, token, siret)
        elif geo_coords:
            result = await _search_by_coords(client, token, geo_coords, radius_m)
        else:
            return None

        if not result:
            return None

        # Étape 3: Analyser le code NAF
        naf_code = result.get("activitePrincipale", "").split(".")[0]  # "45.20A" -> "45"
        naf_label = result.get("activitePrincipaleEtablissement", "")

        type_etablissement = _classify_naf(naf_code)

        return {
            "siret": result.get("siret"),
            "naf_code": naf_code,
            "naf_label": naf_label,
            "type_etablissement": type_etablissement,
            "confiance": 0.9 if type_etablissement != "inconnu" else 0.3,
            "effectifs": result.get("effectifsEtablissement"),
            "date_creation": result.get("dateCreationEtablissement"),
            "nom_entreprise": result.get("denominationUsuelleEtablissement") or result.get("periodes", [{}])[0].get("enseigne1Etablissement"),
            "adresse": _format_address(result),
            "erreur": None,
        }

    except Exception as exc:
        logger.warning("sirene -- erreur inattendue : %s", exc)
        return {"erreur": str(exc)}


async def _get_oauth_token(client: httpx.AsyncClient) -> str | None:
    """Obtient un token OAuth2 pour l'API INSEE."""
    try:
        resp = await client.post(
            "https://api.insee.fr/token",
            data={
                "grant_type": "client_credentials",
                "client_id": settings.insee_client_id,
                "client_secret": settings.insee_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("access_token")
    except Exception as exc:
        logger.warning("sirene -- échec OAuth2 : %s", exc)
        return None


async def _search_by_siret(client: httpx.AsyncClient, token: str, siret: str) -> dict | None:
    """Recherche un établissement par SIRET."""
    try:
        resp = await client.get(
            f"https://api.insee.fr/entreprises/siret/v3/etablissements/{siret}",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("etablissement")
    except Exception as exc:
        logger.warning("sirene -- échec recherche SIRET %s : %s", siret, exc)
        return None


async def _search_by_coords(
    client: httpx.AsyncClient,
    token: str,
    geo_coords: tuple[float, float],
    radius_m: int,
) -> dict | None:
    """Recherche les établissements autour de coordonnées géographiques."""
    lat, lon = geo_coords
    try:
        # Utiliser l'API de recherche géographique de SIRENE
        resp = await client.get(
            "https://api.insee.fr/entreprises/siret/v3/etablissements",
            params={
                "geo": f"lat:{lat};lon:{lon};dist:{radius_m}",
                "nombre": 1,  # Prendre le plus proche
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        etablissements = data.get("etablissements", [])
        return etablissements[0] if etablissements else None
    except Exception as exc:
        logger.warning("sirene -- échec recherche géographique : %s", exc)
        return None


def _classify_naf(naf_code: str) -> str:
    """
    Classifie un établissement selon son code NAF.

    Retourne :
      - "industriel" : usine, entrepôt, manufacture
      - "bureaux" : bureaux, services, informatique
      - "commercial" : commerce, vente
      - "inconnu" : code non reconnu
    """
    if not naf_code:
        return "inconnu"

    section = naf_code[0]  # Première lettre (section NAF)

    # Sections industrielles (A, B, C, D, E, F)
    if section in {"A", "B", "C", "D", "E", "F"}:
        return "industriel"

    # Sections bureaux/services (J, K, L, M, N, O, P, Q, R, S)
    if section in {"J", "K", "L", "M", "N", "O", "P", "Q", "R", "S"}:
        return "bureaux"

    # Sections commerciales (G, H, I)
    if section in {"G", "H", "I"}:
        return "commercial"

    # Sections transport/construction (F, G, H)
    if naf_code[:2] in CODES_NAF_INDUSTRIELS:
        return "industriel"

    if naf_code[:2] in CODES_NAF_BUREAUX:
        return "bureaux"

    return "inconnu"


def _format_address(etablissement: dict) -> str | None:
    """Formate l'adresse complète d'un établissement SIRENE."""
    adresse_elem = etablissement.get("adresseEtablissement", {})
    if not adresse_elem:
        return None

    parts = []
    if adresse_elem.get("numeroVoieEtablissement"):
        parts.append(adresse_elem["numeroVoieEtablissement"])
    if adresse_elem.get("typeVoieEtablissement"):
        parts.append(adresse_elem["typeVoieEtablissement"])
    if adresse_elem.get("libelleVoieEtablissement"):
        parts.append(adresse_elem["libelleVoieEtablissement"])
    if adresse_elem.get("codePostalEtablissement"):
        parts.append(adresse_elem["codePostalEtablissement"])
    if adresse_elem.get("libelleCommuneEtablissement"):
        parts.append(adresse_elem["libelleCommuneEtablissement"])

    return " ".join(parts) if parts else None