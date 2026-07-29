"""Recherche controlee du site officiel d'une entreprise avec Mistral Web Search."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from urllib.parse import urlparse

from app.core.config import settings
from app.recommandations.mistral_client import get_client

SEARCH_MODEL = "mistral-medium-latest"
EXCLUDED_HOSTS = {
    "annuaire-entreprises.data.gouv.fr",
    "data.ademe.fr",
    "france-renov.gouv.fr",
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "pagesjaunes.fr",
    "societe.com",
    "verif.com",
}


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
    identifiant = entreprise.get("siret") or entreprise.get("siren") or "inconnu"
    localisation = " ".join(
        str(entreprise.get(key) or "") for key in ("adresse", "code_postal", "commune")
    ).strip()
    prompt = (
        "Recherche les coordonnees de contact officielles de cette entreprise francaise. "
        "Identifie-la strictement avec son nom, son SIREN/SIRET et sa localisation. "
        "Consulte en priorite son site officiel et sa page contact. N'invente aucune donnee. "
        "N'utilise ni reseau social ni fiche d'une autre entreprise. "
        "Termine avec exactement trois lignes: SITE_OFFICIEL, TELEPHONE et EMAIL. "
        "Mets INCONNU pour chaque valeur non confirmee. "
        f"Nom: {entreprise.get('nom_entreprise') or entreprise.get('nom_complet')}. "
        f"SIREN/SIRET: {identifiant}. Localisation: {localisation}."
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
    except Exception:
        return empty


async def trouver_site_officiel(entreprise: dict[str, Any]) -> str | None:
    return (await enrichir_coordonnees(entreprise))["site_officiel"]
