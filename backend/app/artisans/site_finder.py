"""Recherche controlee du site officiel d'une entreprise avec Mistral Web Search."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.core.logging import get_logger
from app.recommandations.mistral_client import get_client

logger = get_logger(__name__)

SEARCH_MODEL = "mistral-medium-latest"
EXCLUDED_HOSTS = {
    "annuaire-entreprises.data.gouv.fr",
    "bilansgratuits.fr",
    "bodacc.fr",
    "bvdinfo.com",
    "data.ademe.fr",
    "dirigeant.com",
    "facebook.com",
    "france-renov.gouv.fr",
    "hoodspot.fr",
    "indexa.fr",
    "infogreffe.fr",
    "instagram.com",
    "kompass.com",
    "linkedin.com",
    "maison.fr",
    "manageo.fr",
    "pagesjaunes.fr",
    "pappers.fr",
    "score3.fr",
    "societe.com",
    "twitter.com",
    "verif.com",
    "wikipedia.org",
    "x.com",
    "youtube.com",
}

LEGAL_PREFIXES_RE = re.compile(
    r"^(?:MONSIEUR|MADAME|MLLE|M\.|MME|SARL|SAS|SASU|EURL|EI|E\.I\.|S\.A\.R\.L\.|S\.A\.S\.|E\.U\.R\.L\.|SA|S\.A\.|SCOP|SNC|SELARL)\s+",
    re.IGNORECASE,
)
LEGAL_SUFFIXES_RE = re.compile(
    r"\s+(?:SARL|SAS|SASU|EURL|EI|E\.I\.|S\.A\.R\.L\.|S\.A\.S\.|E\.U\.R\.L\.|SA|S\.A\.|SCOP|SNC|SELARL)$",
    re.IGNORECASE,
)


def _nettoyer_nom_entreprise(nom: str) -> str:
    res = (nom or "").strip()
    while True:
        cleaned = LEGAL_PREFIXES_RE.sub("", res).strip()
        if cleaned == res:
            break
        res = cleaned
    res = LEGAL_SUFFIXES_RE.sub("", res).strip()
    return res or (nom or "").strip()


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def _url_candidate(value: Any) -> str | None:
    raw = str(value or "").strip().rstrip(".,);]}>")
    if not raw:
        return None
    url = raw if re.match(r"^https?://", raw, re.IGNORECASE) else f"https://{raw}"
    host = _host(url)
    if not host or "." not in host:
        return None
    if host in EXCLUDED_HOSTS or any(host.endswith(f".{item}") for item in EXCLUDED_HOSTS):
        return None
    return url


def _response_data(response: Any) -> tuple[list[str], list[str]]:
    payload = response.model_dump() if hasattr(response, "model_dump") else response
    urls: list[str] = []
    texts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("url"):
                urls.append(str(value["url"]))
            if value.get("type") == "text" and value.get("text"):
                texts.append(str(value["text"]))
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(payload)
    return list(dict.fromkeys(urls)), texts


def _extract_contact(response: Any) -> dict[str, str | None]:
    references, texts = _response_data(response)
    text = "\n".join(texts)
    reference_hosts = {_host(url) for url in references}

    site_match = re.search(r"SITE_OFFICIEL\s*:\s*(https?://[^\s\"'<>]+)", text, re.IGNORECASE)
    site = _url_candidate(site_match.group(1)) if site_match else None
    if site and _host(site) not in reference_hosts:
        site = None

    phone_match = re.search(r"TELEPHONE\s*:\s*([+()\d][+()\d .-]{7,24})", text, re.IGNORECASE)
    phone = re.sub(r"\s+", " ", phone_match.group(1)).strip(" .-") if phone_match else None

    email_match = re.search(
        r"EMAIL\s*:\s*([A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
        text,
        re.IGNORECASE,
    )
    email = email_match.group(1).lower() if email_match else None
    return {"site_officiel": site, "telephone": phone, "email": email}


def _search_sync(entreprise: dict[str, Any]) -> dict[str, str | None]:
    raw_nom = str(entreprise.get("nom_entreprise") or entreprise.get("nom_complet") or "").strip()
    nom_nettoye = _nettoyer_nom_entreprise(raw_nom)
    commune = str(entreprise.get("commune") or "").strip()
    code_postal = str(entreprise.get("code_postal") or "").strip()
    adresse = str(entreprise.get("adresse") or "").strip()
    identifiant = str(entreprise.get("siret") or entreprise.get("siren") or "inconnu").strip()
    activite = str(entreprise.get("libelle") or entreprise.get("activite_principale") or "").strip()

    localisation_recherche = f"{commune} {code_postal}".strip() or adresse
    query_cible = f"{nom_nettoye} {localisation_recherche} site officiel".strip()

    prompt = (
        f"Trouve le VRAI site web officiel d'entreprise et les coordonnees de contact direct pour: '{nom_nettoye}'.\n\n"
        f"RECHERCHE PRINCIPALE SUR LE WEB: Utilise la requete de recherche '{query_cible}' ou '{nom_nettoye} {commune}'.\n\n"
        "DIRECTIVES STRICTES:\n"
        "1. Ne retiens JAMAIS un annuaire public, registre legal ou reseau social (ex: societe.com, pappers.fr, annuaire-entreprises.data.gouv.fr, infogreffe.fr, pagesjaunes.fr, facebook.com, linkedin.com, etc.). Seul le vrai domaine web officiel de l'entreprise est accepte.\n"
        "2. Utilise le SIREN/SIRET et l'adresse uniquement pour VERIFIER en second lieu que l'entreprise trouvee correspond bien a la societe cible.\n"
        "3. Si l'entreprise n'a aucun site web propre officiel, indique SITE_OFFICIEL: INCONNU.\n"
        "4. N'invente aucune URL, telephone ou email.\n\n"
        "CONTEXTE DE VERIFICATION:\n"
        f"- Nom legal complet: {raw_nom}\n"
        f"- Nom d'usage/recherche: {nom_nettoye}\n"
        f"- SIREN/SIRET: {identifiant}\n"
        f"- Adresse / Commune: {adresse} {code_postal} {commune}\n"
        f"- Activite / Metier: {activite}\n\n"
        "Reponds STRICTEMENT avec exactement 3 lignes a la fin:\n"
        "SITE_OFFICIEL: <url du vrai site officiel ou INCONNU>\n"
        "TELEPHONE: <numero ou INCONNU>\n"
        "EMAIL: <email ou INCONNU>"
    )
    response = get_client().beta.conversations.start(
        model=SEARCH_MODEL,
        inputs=prompt,
        tools=[{"type": "web_search"}],
        instructions=(
            "Tu verifies les coordonnees d'entreprises. Cite les pages web consultees "
            "et ne devine jamais une URL, un numero ou un e-mail."
        ),
        store=False,
    )
    return _extract_contact(response)


async def enrichir_coordonnees(entreprise: dict[str, Any]) -> dict[str, str | None]:
    empty = {"site_officiel": None, "telephone": None, "email": None}
    if not settings.mistral_api_key:
        return empty
    try:
        return await asyncio.to_thread(_search_sync, entreprise)
    except Exception as exc:
        logger.debug("Échec enrichissement web pour %s: %s", entreprise.get("nom_entreprise"), exc)
        return empty


async def trouver_site_officiel(entreprise: dict[str, Any]) -> str | None:
    return (await enrichir_coordonnees(entreprise))["site_officiel"]

