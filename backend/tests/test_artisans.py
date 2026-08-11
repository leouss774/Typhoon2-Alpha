"""Tests hors ligne du service de matching artisans."""

from __future__ import annotations

import unittest
from unittest.mock import patch

import httpx

from app.artisans.service import classifier_recommandation, extraire_code_postal, matcher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeClient:
    async def get(self, url, params):
        if "ademe.fr" in url:
            return FakeResponse({"results": [{
                "siret": "12345678900012",
                "nom_entreprise": "Isolation Test",
                "adresse": "1 rue du Test",
                "code_postal": "33000",
                "commune": "Bordeaux",
                "telephone": "0102030405",
                "site_internet": "https://isolation-test.fr/contact",
                "lien_date_fin": "2099-12-31",
            }]})
        return FakeResponse({"results": [{
            "siren": "987654321",
            "nom_complet": "Géotechnique Test",
            "etat_administratif": "A",
            "date_creation": "2010-01-01",
            "activite_principale": "71.12B",
            "siege": {
                "adresse": "2 rue du Test",
                "code_postal": "33000",
                "libelle_commune": "Bordeaux",
            },
        }]})


class ArtisansServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_code_postal_et_classification(self):
        self.assertEqual(extraire_code_postal("12 rue des Lilas, 33000 Bordeaux"), "33000")
        self.assertEqual(classifier_recommandation("toiture", [], "Isolation des combles"), "isolation_combles")
        self.assertEqual(
            classifier_recommandation("fondations", ["retrait_gonflement_argiles"], "Diagnostic"),
            "rga_geotechnique",
        )
        self.assertEqual(
            classifier_recommandation("murs_ouest", [], "Respecter les techniques locales"),
            "travaux_facade",
        )

    async def test_matching_rge_et_non_rge(self):
        result = await matcher(
            "12 rue des Lilas, 33000 Bordeaux",
            [
                {"zone": "toiture", "risques": [], "recommandations": [{"mesure": "Isolation des combles"}]},
                {
                    "zone": "fondations",
                    "risques": ["retrait_gonflement_argiles"],
                    "recommandations": [{"mesure": "Faire réaliser un diagnostic"}],
                },
            ],
            client=FakeClient(),
        )
        self.assertEqual(result["code_postal"], "33000")
        self.assertEqual(len(result["recommandations_traitees"]), 2)
        for groupe in result["recommandations_traitees"]:
            self.assertEqual(groupe["entreprises"][0]["score_objectif_sur_100"], 100)
        rge, non_rge = result["recommandations_traitees"]
        # Site natif ADEME/RGE conservé tel quel.
        self.assertEqual(rge["entreprises"][0]["site_officiel"], "https://isolation-test.fr/contact")
        # Sans recherche web (Mistral web_search supprimé) : le candidat non-RGE
        # (Sirene) n'a aucune coordonnée native — pas de site, pas de contact.
        self.assertIsNone(non_rge["entreprises"][0].get("site_officiel"))
        self.assertFalse(non_rge["entreprises"][0].get("telephone"))
        self.assertFalse(non_rge["entreprises"][0].get("email"))
        # type_lien existe mais reste None : plus jamais taggé "web_search".
        self.assertIsNone(non_rge["entreprises"][0].get("type_lien"))
        self.assertNotIn("lien_fiche_officielle", non_rge["entreprises"][0])

    async def test_source_indisponible_ne_fait_pas_echouer_le_rapport(self):
        async def broken(_request):
            raise httpx.ConnectError("offline")

        client = httpx.AsyncClient(transport=httpx.MockTransport(broken))
        try:
            result = await matcher(
                "33000 Bordeaux",
                [{"zone": "toiture", "risques": [], "recommandations": [{"mesure": "Isolation des combles"}]}],
                client=client,
            )
        finally:
            await client.aclose()
        self.assertEqual(result["recommandations_traitees"][0]["entreprises"], [])
        self.assertIn("indisponible", result["recommandations_traitees"][0]["erreur"])


if __name__ == "__main__":
    unittest.main()
