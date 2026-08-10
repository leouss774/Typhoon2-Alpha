# -*- coding: utf-8 -*-
"""Tests hors ligne de la résolution de logo — app/artisans/logo.py.

Couvre :
  - le garde-fou SSRF (hôtes privés/loopback rejetés, schéma non-http rejeté),
  - la reconnaissance de signatures binaires (PNG/JPEG/GIF/ICO/WEBP/SVG),
  - l'extraction et le classement des <link rel="icon"> de la page d'accueil
    (apple-touch-icon d'abord, puis icônes par taille déclarée décroissante),
  - la résolution complète via MockTransport : vrai logo de la page d'accueil
    préféré à /favicon.ico (repli), fallback octet-stream par signature,
  - la mémorisation d'un hôte sans logo (pas de re-tentative).
"""

from __future__ import annotations

import base64
import socket
import unittest
from unittest.mock import patch

import httpx

from app.artisans import logo as logo_module
from app.artisans.logo import (
    _extraire_icones,
    _hote_public,
    _ressemble_image,
    trouver_favicon,
)

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
_IP_PUBLIQUE = ("93.184.216.34", 0)


def _getaddrinfo_public(hostname: str, port: int | None = None) -> list[tuple]:
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, hostname, _IP_PUBLIQUE)]


class HotePublicTests(unittest.TestCase):
    def test_schema_non_http_rejete(self):
        self.assertIsNone(_hote_public("ftp://exemple.fr/favicon.ico"))
        self.assertIsNone(_hote_public("file:///etc/passwd"))
        self.assertIsNone(_hote_public(""))

    def test_loopback_et_prive_rejetes(self):
        # Adresses littérales : résolution locale, aucun DNS nécessaire.
        self.assertIsNone(_hote_public("http://127.0.0.1/x"))
        self.assertIsNone(_hote_public("http://[::1]/x"))
        self.assertIsNone(_hote_public("http://192.168.1.10/x"))
        self.assertIsNone(_hote_public("http://10.0.0.5/x"))
        self.assertIsNone(_hote_public("http://169.254.169.254/latest/meta-data/"))  # lien-local

    def test_hote_public_accepte(self):
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            self.assertEqual(_hote_public("https://www.exemple.fr:8443/path"), "www.exemple.fr")

    def test_hote_avec_une_ip_privee_rejete(self):
        infos = _getaddrinfo_public("exemple.fr") + [(socket.AF_INET, socket.SOCK_STREAM, 6, "exemple.fr", ("127.0.0.1", 0))]
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=infos):
            self.assertIsNone(_hote_public("https://exemple.fr/"))


class RessembleImageTests(unittest.TestCase):
    def test_signatures_connues(self):
        self.assertTrue(_ressemble_image(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8))             # PNG
        self.assertTrue(_ressemble_image(b"\xff\xd8\xff\xe0" + b"\x00" * 8))              # JPEG
        self.assertTrue(_ressemble_image(b"GIF89a" + b"\x00" * 8))                         # GIF
        self.assertTrue(_ressemble_image(b"\x00\x00\x01\x00" + b"\x00" * 8))               # ICO
        self.assertTrue(_ressemble_image(b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 8))       # WEBP
        self.assertTrue(_ressemble_image(b"<svg xmlns='http://www.w3.org/2000/svg'>"))     # SVG

    def test_contenu_non_image_rejete(self):
        self.assertFalse(_ressemble_image(b"<!DOCTYPE html><html>"))
        self.assertFalse(_ressemble_image(b"not an image at all"))


class ExtraireIconesTests(unittest.TestCase):
    def test_rel_icon_et_shortcut_icon(self):
        html = (
            '<html><head>'
            '<link rel="icon" href="/favicon.png">'
            '<link rel="shortcut icon" href="/fav.ico">'
            '<link rel="apple-touch-icon" href="/apple.png">'
            '<link rel="stylesheet" href="/style.css">'
            '</head></html>'
        )
        icones = _extraire_icones(html)
        hrefs = [href for href, _ in icones]
        self.assertIn("/favicon.png", hrefs)
        self.assertIn("/fav.ico", hrefs)
        self.assertIn("/apple.png", hrefs)
        self.assertNotIn("/style.css", hrefs)

    def test_apple_touch_icon_classe_en_premier(self):
        html = (
            '<html><head>'
            '<link rel="icon" href="/favicon.png">'
            '<link rel="apple-touch-icon" href="/apple.png">'
            '</head></html>'
        )
        icones = _extraire_icones(html)
        self.assertEqual(icones[0], ("/apple.png", (0, 0)))
        self.assertEqual(icones[1][0], "/favicon.png")

    def test_icone_la_plus_grande_declaree_d_abord(self):
        html = (
            '<html><head>'
            '<link rel="icon" sizes="16x16" href="/fav-16.png">'
            '<link rel="icon" sizes="192x192" href="/fav-192.png">'
            '</head></html>'
        )
        icones = _extraire_icones(html)
        self.assertEqual(icones[0], ("/fav-192.png", (1, -192)))
        self.assertEqual(icones[1], ("/fav-16.png", (1, -16)))


class TrouverFaviconTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        logo_module.favicon_cache.clear()

    async def test_favicon_ico_en_repli_quand_pas_d_icone_lien(self):
        """Sans <link rel="icon"> sur la page d'accueil, /favicon.ico sert de repli."""
        requetes: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requetes.append(request.url.path)
            if request.url.path == "/":
                return httpx.Response(200, text="<html><head></head></html>", headers={"content-type": "text/html"})
            if request.url.path == "/favicon.ico":
                return httpx.Response(200, content=_PNG, headers={"content-type": "image/png"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            async with httpx.AsyncClient(transport=transport) as client:
                resultat = await trouver_favicon("https://exemple.fr", client=client)
        self.assertEqual(resultat, (_PNG, "image/png"))
        self.assertEqual(requetes, ["/", "/favicon.ico"])

    async def test_vrai_logo_apple_touch_prefere_au_favicon_ico(self):
        """Le vrai logo (apple-touch-icon) est servi même si /favicon.ico existe."""
        requetes: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requetes.append(request.url.path)
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    text='<html><head><link rel="apple-touch-icon" href="/apple-180.png"></head></html>',
                    headers={"content-type": "text/html"},
                )
            if request.url.path == "/apple-180.png":
                return httpx.Response(200, content=_PNG, headers={"content-type": "image/png"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            async with httpx.AsyncClient(transport=transport) as client:
                resultat = await trouver_favicon("https://exemple.fr", client=client)
        self.assertEqual(resultat, (_PNG, "image/png"))
        self.assertEqual(requetes, ["/", "/apple-180.png"])  # /favicon.ico jamais appelé

    async def test_favicon_via_link_rel_icon(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    text='<html><head><link rel="icon" href="/assets/fav.png"></head></html>',
                    headers={"content-type": "text/html"},
                )
            if request.url.path == "/assets/fav.png":
                return httpx.Response(200, content=_PNG, headers={"content-type": "image/png"})
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            async with httpx.AsyncClient(transport=transport) as client:
                resultat = await trouver_favicon("https://exemple.fr", client=client)
        self.assertEqual(resultat, (_PNG, "image/png"))

    async def test_favicon_octet_stream_accepte_par_signature(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=_PNG, headers={"content-type": "application/octet-stream"})

        transport = httpx.MockTransport(handler)
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            async with httpx.AsyncClient(transport=transport) as client:
                resultat = await trouver_favicon("https://exemple.fr", client=client)
        self.assertEqual(resultat, (_PNG, "image/x-icon"))

    async def test_favicon_inline_data_uri_decode_sans_requete_http(self):
        """Un favicon déclaré en data:image/...;base64 (ex. dhome-renovation.fr)
        est décodé localement — aucune requête HTTP pour l'icône."""
        png_b64 = base64.b64encode(_PNG).decode()
        requetes: list[str] = []

        async def handler(request: httpx.Request) -> httpx.Response:
            requetes.append(request.url.path)
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    text=(
                        '<html><head><link rel="icon" type="image/png" '
                        f'href="data:image/png;base64,{png_b64}"></head></html>'
                    ),
                    headers={"content-type": "text/html"},
                )
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            async with httpx.AsyncClient(transport=transport) as client:
                resultat = await trouver_favicon("https://exemple.fr", client=client)
        self.assertEqual(resultat, (_PNG, "image/png"))
        self.assertEqual(requetes, ["/"])  # aucune requête pour l'icône (inline)

    async def test_aucun_favicon_retourne_none_et_est_memorise(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(404)

        transport = httpx.MockTransport(handler)
        with patch("app.artisans.logo.socket.getaddrinfo", return_value=_getaddrinfo_public("exemple.fr")):
            async with httpx.AsyncClient(transport=transport) as client:
                resultat = await trouver_favicon("https://exemple.fr", client=client)
        self.assertIsNone(resultat)
        # Même hôte, autre chemin : le « absent » est mémorisé (aucune requête).
        self.assertIsNone(await trouver_favicon("https://exemple.fr/autre", client=client))


if __name__ == "__main__":
    unittest.main()
