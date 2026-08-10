# -*- coding: utf-8 -*-
"""Résolution du logo d'entreprise (endpoint /api/v1/artisans/logo).

Récupère le logo réel d'un site d'entreprise (site_officiel) :
  1. SSRF guard : l'hôte doit résoudre exclusivement vers des IP publiques
     (jamais loopback / privé / lien-local / réservé / multicast).
  2. Résolution : les <link rel="icon"> de la page d'accueil d'abord, en
     préférant l'apple-touch-icon (le vrai logo, >= 180 px) puis les icônes
     déclarées les plus grandes ; /favicon.ico (souvent un 16 px générique)
     n'est qu'un repli.
  3. Garde-fous : content-type image/* (ou signature binaire reconnue),
     taille plafonnée (512 Ko), timeout court (4 s).
  4. Cache mémoire par hôte (TTLCache 24 h) — un logo introuvable est
     mémorisé pour ne pas marteler le site.

Le frontend superpose le logo sur l'avatar à initiales de la carte ; en cas
d'échec (404), les initiales restent affichées (fallback onError). Les
initiales ne servent que de dernier recours : aucune source de logo n'existe
pour une entreprise sans site web (registres publics Sirene/ADEME).
"""

from __future__ import annotations

import ipaddress
import socket
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import httpx

from app.core.logging import get_logger
from app.matching.cache import TTLCache

logger = get_logger(__name__)

FAVICON_TIMEOUT_SECONDS = 4.0
FAVICON_MAX_BYTES = 512 * 1024  # 512 Ko — un favicon est minuscule

# Cache par hôte : clé = hôte (le favicon ne change presque jamais).
favicon_cache = TTLCache(maxsize=1024, ttl_seconds=86400)

# Sentinelle : favicon introuvable pour cet hôte (pas de re-tentative pendant le TTL).
_ABSENT = (b"", "")


def _hote_public(url: str) -> str | None:
    """Hôte de l'URL si http(s) et résolvant uniquement vers des IP publiques."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower().rstrip(".")
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return None
    for info in infos:
        try:
            ip = ipaddress.ip_address(info[4][0])
        except ValueError:
            return None
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return None
    return host


def _ressemble_image(contenu: bytes) -> bool:
    """Signature binaire connue (PNG/JPEG/GIF/ICO/WEBP/SVG) — accepte un
    favicon.ico servi avec un content-type inexact (ex. octet-stream)."""
    debut = contenu.lstrip()[:200].lower()
    return bool(
        contenu[:8] == b"\x89PNG\r\n\x1a\n"
        or contenu[:6] in (b"GIF87a", b"GIF89a")
        or contenu[:3] == b"\xff\xd8\xff"
        or (contenu[:4] == b"RIFF" and contenu[8:12] == b"WEBP")
        or contenu[:4] == b"\x00\x00\x01\x00"  # ICO
        or debut.startswith(b"<svg")
        or (debut.startswith(b"<?xml") and b"<svg" in debut)
        or debut.startswith(b"<!doctype svg")
    )


def _est_image(resp: httpx.Response, tolere_octet_stream: bool = False) -> bool:
    if len(resp.content) > FAVICON_MAX_BYTES:
        return False
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    if content_type.startswith("image/"):
        return True
    return tolere_octet_stream and _ressemble_image(resp.content)


def _media_type(resp: httpx.Response) -> str:
    """Media type déclaré s'il est image/*, sinon image/x-icon (cas où le
    favicon n'a été accepté que par sa signature binaire)."""
    content_type = (resp.headers.get("content-type") or "").split(";")[0].strip().lower()
    return content_type if content_type.startswith("image/") else "image/x-icon"


def _taille_declaree(sizes: str) -> int:
    """Plus grande largeur déclarée (ex. "16x16 32x32" -> 32 ; "any" -> 0)."""
    meilleure = 0
    for partie in sizes.lower().split():
        if "x" in partie:
            largeur = partie.split("x")[0]
            if largeur.isdigit():
                meilleure = max(meilleure, int(largeur))
    return meilleure


class _IconParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        # (href, priorité) — priorité comparable : apple-touch-icon (0, 0)
        # d'abord, puis icon par taille déclarée décroissante.
        self.icones: list[tuple[str, tuple[int, int]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "link":
            return
        attributs = {k.lower(): (v or "") for k, v in attrs}
        rel = attributs.get("rel", "").lower()
        href = attributs.get("href")
        if not href:
            return
        rels = rel.split()
        if "apple-touch-icon" in rels:
            self.icones.append((href, (0, 0)))  # le vrai logo du site
        elif "icon" in rels or rel == "shortcut icon":
            self.icones.append((href, (1, -_taille_declaree(attributs.get("sizes", "")))))


def _extraire_icones(html: str) -> list[tuple[str, tuple[int, int]]]:
    """Icônes de la page d'accueil, triées : apple-touch-icon d'abord, puis
    les icônes par taille déclarée décroissante (les plus grandes d'abord)."""
    parser = _IconParser()
    try:
        parser.feed(html[:FAVICON_MAX_BYTES])
    except Exception:
        return []
    parser.icones.sort(key=lambda item: item[1])
    return parser.icones


async def _telecharger(client: httpx.AsyncClient, url: str) -> httpx.Response | None:
    try:
        resp = await client.get(url, timeout=FAVICON_TIMEOUT_SECONDS, follow_redirects=True)
        resp.raise_for_status()
        return resp
    except httpx.HTTPError:
        return None


async def trouver_favicon(url: str, client: httpx.AsyncClient | None = None) -> tuple[bytes, str] | None:
    """Favicon d'un site d'entreprise : (contenu, media_type) ou None.

    `client` est optionnel (tests hors ligne) ; sinon un client dédié est créé.
    """
    host = _hote_public(url)
    if not host:
        return None

    cache_key = host
    cached = favicon_cache.get(cache_key)
    if cached == _ABSENT:
        return None
    if cached is not None:
        return cached  # type: ignore[return-value]

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient()

    try:
        base = f"https://{host}"
        # 1. Vrai logo : <link rel="icon"> de la page d'accueil, en préférant
        #    l'apple-touch-icon (logo réel >= 180 px) puis les icônes déclarées
        #    les plus grandes — bien meilleur rendu que le favicon.ico 16 px.
        page = await _telecharger(client, f"{base}/")
        if page is not None:
            for href, _priorite in _extraire_icones(page.text):
                icon_url = urljoin(f"{base}/", href)
                if not _hote_public(icon_url):
                    continue
                icon = await _telecharger(client, icon_url)
                if icon is not None and _est_image(icon):
                    media = _media_type(icon)
                    favicon_cache.set(cache_key, (icon.content, media))
                    return icon.content, media

        # 2. Repli : /favicon.ico — content-type tolérant (beaucoup de
        #    serveurs servent l'icône en octet-stream).
        resp = await _telecharger(client, f"{base}/favicon.ico")
        if resp is not None and _est_image(resp, tolere_octet_stream=True):
            media = _media_type(resp)
            favicon_cache.set(cache_key, (resp.content, media))
            return resp.content, media

        favicon_cache.set(cache_key, _ABSENT)
        return None
    finally:
        if owns_client:
            await client.aclose()
