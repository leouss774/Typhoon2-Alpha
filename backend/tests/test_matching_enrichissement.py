# -*- coding: utf-8 -*-
"""Tests hors ligne de l'enrichissement simple des profils artisans
(_enrichir_simples) — aucune vérification, les boutons du frontend sont
exposés dès que la donnée existe (native ou trouvée par recherche web).

Couvre :
  - l'enrichissement de TOUTES les entreprises incomplètes (pas de budget,
    pas d'early stop) — site et/ou contact trouvés conservés tels quels,
  - la conservation des résultats partiels (site seul, contact seul),
  - l'absence totale de drapeaux de vérification dans la réponse,
  - la suppression des champs internes (score, lien de fiche, site_internet),
  - la notice pour un groupe entièrement vide de données.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch

from app.matching import service as matching_service


def _cand(
    name: str,
    site: str | None = None,
    tel: str | None = None,
    email: str | None = None,
    siret: str | None = None,
    siren: str | None = None,
) -> dict:
    return {
        "nom_entreprise": name, "siret": siret, "siren": siren,
        "site_internet": site, "telephone": tel, "email": email,
        "score_objectif_sur_100": 90, "details_score": ["x"],
        "lien_fiche_officielle": "https://annuaire-entreprises.data.gouv.fr/entreprise/1",
    }


def _lookup_ok(counter: dict) -> object:
    """Fausse recherche web complète : site + contact toujours trouvés."""

    async def lookup(entreprise: dict) -> dict:
        counter["n"] += 1
        site = entreprise.get("site_internet") or entreprise.get("site_officiel")
        if site:
            return {"site_officiel": site, "telephone": "0102030405", "email": "c@x.fr"}
        return {"site_officiel": "https://decouvert.fr", "telephone": "0600000000", "email": "d@x.fr"}

    return lookup


class EnrichirSimplesTests(unittest.IsolatedAsyncioTestCase):
    """Scénarios d'enrichissement sans gating."""

    async def test_toutes_les_entreprises_incompletes_sont_enrichies(self):
        counter = {"n": 0}
        resultats = [{"entreprises": [
            _cand("A", site="https://a.fr", siret="1"),                # site seul -> contact cherché
            _cand("B", tel="02", siren="2"),                           # contact seul -> site cherché
            _cand("C", site="https://c.fr", tel="03", email="c@c.fr", siret="3"),  # complet -> intact
        ]}]
        with patch.object(matching_service, "enrichir_coordonnees", new=_lookup_ok(counter)):
            await matching_service._enrichir_simples(resultats, limite=5)
        entreprises = resultats[0]["entreprises"]
        self.assertEqual(counter["n"], 2)  # A et B seulement
        self.assertEqual(entreprises[0]["site_officiel"], "https://a.fr")
        self.assertEqual(entreprises[0]["telephone"], "0102030405")  # contact trouvé par la recherche
        self.assertEqual(entreprises[1]["site_officiel"], "https://decouvert.fr")
        self.assertEqual(entreprises[1]["telephone"], "02")  # contact natif conservé
        self.assertEqual(entreprises[2]["telephone"], "03")  # profil complet intact

    async def test_resultat_partiel_conserve_sans_gating(self):
        counter = {"n": 0}

        async def lookup_site_seul(entreprise: dict) -> dict:
            counter["n"] += 1
            return {"site_officiel": "https://trouve.fr"}  # la recherche ne trouve QUE le site

        resultats = [{"entreprises": [
            _cand("A", tel="01", siret="1"),
        ]}]
        with patch.object(matching_service, "enrichir_coordonnees", new=lookup_site_seul):
            await matching_service._enrichir_simples(resultats, limite=5)
        entreprise = resultats[0]["entreprises"][0]
        self.assertEqual(entreprise["site_officiel"], "https://trouve.fr")  # site conservé
        self.assertEqual(entreprise["telephone"], "01")  # contact natif conservé

    async def test_aucun_drapeau_de_verification_ni_champ_interne(self):
        counter = {"n": 0}
        resultats = [{"entreprises": [
            _cand("A", site="https://a.fr", tel="01", email="a@a.fr", siret="1"),
        ]}]
        with patch.object(matching_service, "enrichir_coordonnees", new=_lookup_ok(counter)):
            await matching_service._enrichir_simples(resultats, limite=5)
        entreprise = resultats[0]["entreprises"][0]
        for champ in (
            "profil_verifie", "site_verifie", "contact_verifie",
            "score_objectif_sur_100", "details_score",
            "site_internet", "lien_fiche_officielle",
        ):
            self.assertNotIn(champ, entreprise)

    async def test_notice_pour_groupe_sans_aucune_donnee(self):
        counter = {"n": 0}

        async def lookup_vide(entreprise: dict) -> dict:
            counter["n"] += 1
            return {}

        resultats = [{"entreprises": [
            _cand("A", siren="1"),
            _cand("B", siren="2"),
        ]}]
        with patch.object(matching_service, "enrichir_coordonnees", new=lookup_vide):
            await matching_service._enrichir_simples(resultats, limite=5)
        self.assertIn("restent a confirmer", resultats[0]["notice"])

    async def test_liste_vide_produit_une_notice_explicite(self):
        resultats = [{"entreprises": []}]
        with patch.object(matching_service, "enrichir_coordonnees", new=_lookup_ok({"n": 0})):
            await matching_service._enrichir_simples(resultats, limite=5)
        self.assertEqual(resultats[0]["entreprises"], [])
        self.assertIn("Aucune entreprise active", resultats[0]["notice"])

    async def test_reponse_capee_a_top_n(self):
        """La réponse ne renvoie que `limite` entreprises, pas la liste complète."""
        resultats = [{"entreprises": [_cand(f"E{i}", siren=str(i)) for i in range(8)]}]
        with patch.object(matching_service, "enrichir_coordonnees", new=_lookup_ok({"n": 0})):
            await matching_service._enrichir_simples(resultats, limite=5)
        self.assertEqual(len(resultats[0]["entreprises"]), 5)

    async def test_site_annuaire_fallback_pour_entreprise_sans_site(self):
        """Sans site propre, la fiche de l'annuaire officiel est exposée
        (jamais un faux lien) ; un vrai site garde site_officiel seul."""
        counter = {"n": 0}

        async def lookup_vide(entreprise: dict) -> dict:
            counter["n"] += 1
            return {}

        resultats = [{"entreprises": [
            _cand("Sans site", siren="123456789"),
            _cand("Avec site", site="https://reel.fr", siret="98765432100012"),
        ]}]
        with patch.object(matching_service, "enrichir_coordonnees", new=lookup_vide):
            await matching_service._enrichir_simples(resultats, limite=5)
        sans_site, avec_site = resultats[0]["entreprises"]
        self.assertIsNone(sans_site["site_officiel"])
        self.assertEqual(
            sans_site["site_annuaire"],
            "https://annuaire-entreprises.data.gouv.fr/entreprise/123456789",
        )
        self.assertEqual(avec_site["site_officiel"], "https://reel.fr")
        self.assertNotIn("site_annuaire", avec_site)


if __name__ == "__main__":
    unittest.main()
