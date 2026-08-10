# -*- coding: utf-8 -*-
"""Tests hors ligne de la mise en forme des profils artisans (_enrichir_simples).

Couvre :
  - la conservation des sites officiels natifs (registre ADEME/RGE) qui passent
    le filtre _site_entreprise,
  - le filtrage des domaines d'annuaires (ex: pappers.fr, societe.com),
  - le repli systématique vers site_annuaire ('Fiche entreprise') pour les candidats
    sans site natif,
  - la conservation du téléphone et de l'e-mail natifs,
  - le nettoyage strict des champs internes (score, lien_fiche_officielle, site_internet),
  - la notice pour une liste vide ou sans coordonnées.
"""

from __future__ import annotations

import unittest

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
        "nom_entreprise": name,
        "siret": siret,
        "siren": siren,
        "site_internet": site,
        "telephone": tel,
        "email": email,
        "score_objectif_sur_100": 90,
        "details_score": ["x"],
        "lien_fiche_officielle": "https://annuaire-entreprises.data.gouv.fr/entreprise/1",
    }


class EnrichirSimplesTests(unittest.TestCase):
    """Scénarios de mise en forme native sans appels web."""

    def test_site_officiel_natif_conserve(self):
        resultats = [{"entreprises": [
            _cand("Artisan A", site="https://artisan-a.fr", tel="0102030405", siret="12345678900012"),
        ]}]
        matching_service._enrichir_simples(resultats, limite=5)
        entreprise = resultats[0]["entreprises"][0]
        self.assertEqual(entreprise["site_officiel"], "https://artisan-a.fr")
        self.assertEqual(entreprise["telephone"], "0102030405")
        self.assertNotIn("site_annuaire", entreprise)

    def test_site_annuaire_fallback_si_pas_de_site_natif(self):
        resultats = [{"entreprises": [
            _cand("Artisan B", siren="987654321"),
        ]}]
        matching_service._enrichir_simples(resultats, limite=5)
        entreprise = resultats[0]["entreprises"][0]
        self.assertIsNone(entreprise["site_officiel"])
        self.assertEqual(
            entreprise["site_annuaire"],
            "https://annuaire-entreprises.data.gouv.fr/entreprise/987654321",
        )

    def test_domaine_annuaire_rejette_de_site_officiel(self):
        resultats = [{"entreprises": [
            _cand("Artisan C", site="https://www.pappers.fr/entreprise/123", siren="123456789"),
        ]}]
        matching_service._enrichir_simples(resultats, limite=5)
        entreprise = resultats[0]["entreprises"][0]
        self.assertIsNone(entreprise["site_officiel"])
        self.assertEqual(
            entreprise["site_annuaire"],
            "https://annuaire-entreprises.data.gouv.fr/entreprise/123456789",
        )

    def test_nettoyage_champs_internes(self):
        resultats = [{"entreprises": [
            _cand("Artisan D", site="https://d.fr", tel="01", siret="1"),
        ]}]
        matching_service._enrichir_simples(resultats, limite=5)
        entreprise = resultats[0]["entreprises"][0]
        for champ in (
            "profil_verifie", "site_verifie", "contact_verifie",
            "score_objectif_sur_100", "details_score",
            "site_internet", "lien_fiche_officielle",
        ):
            self.assertNotIn(champ, entreprise)

    def test_reponse_capee_a_top_n(self):
        resultats = [{"entreprises": [_cand(f"E{i}", siren=str(i)) for i in range(8)]}]
        matching_service._enrichir_simples(resultats, limite=5)
        self.assertEqual(len(resultats[0]["entreprises"]), 5)

    def test_liste_vide_produit_une_notice_explicite(self):
        resultats = [{"entreprises": []}]
        matching_service._enrichir_simples(resultats, limite=5)
        self.assertEqual(resultats[0]["entreprises"], [])
        self.assertIn("Aucune entreprise active", resultats[0]["notice"])


if __name__ == "__main__":
    unittest.main()
