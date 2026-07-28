"""
Teste executer_cycle_suivi_reel en mockant les appels réseau, car ce
bac à sable ne peut pas atteindre georisques.gouv.fr ni api.cquest.org
(domaines non whitelistés ici). À exécuter réellement dans votre propre
environnement pour valider les vrais appels HTTP.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from agents import monitoring_agent
from connectors import dvf_connector, georisques_connector


class TestCycleSuiviReel(unittest.TestCase):
    @patch.object(georisques_connector, "evenements_catnat", return_value=[{"id": 1}])
    @patch.object(georisques_connector, "exposition_rga", return_value={"code_exposition": "3", "exposition": "Exposition forte"})
    @patch.object(dvf_connector, "prix_m2_median", return_value=3200.0)
    def test_marche_en_hausse_et_risque_degrade(self, mock_prix, mock_rga, mock_catnat):
        resultat = monitoring_agent.executer_cycle_suivi_reel(
            lat=47.39, lon=0.68,
            valeur_reference=330000,
            prix_m2_reference=3000.0,  # référence plus basse -> marché en hausse
            capital_restant_du=250000,
            code_exposition_rga_reference="2",  # référence différente -> alerte
            nb_catnat_reference=0,
        )
        self.assertEqual(resultat["marche"]["statut"], "ok")
        self.assertAlmostEqual(resultat["marche"]["ratio_evolution_marche"], 3200 / 3000, places=4)
        self.assertTrue(resultat["risque"]["alertes"])  # doit détecter le changement RGA
        self.assertTrue(resultat["reexpertise_requise"])  # car alerte de risque détectée

    @patch.object(georisques_connector, "evenements_catnat", side_effect=georisques_connector.GeorisquesIndisponible("timeout simulé"))
    @patch.object(dvf_connector, "prix_m2_median", side_effect=dvf_connector.DVFIndisponible("connexion simulée impossible"))
    def test_api_indisponibles_ne_plantent_pas_le_cycle(self, mock_prix, mock_catnat):
        resultat = monitoring_agent.executer_cycle_suivi_reel(
            lat=47.39, lon=0.68,
            valeur_reference=330000,
            prix_m2_reference=3000.0,
            capital_restant_du=250000,
        )
        self.assertEqual(resultat["marche"]["statut"], "indisponible")
        self.assertEqual(resultat["risque"]["statut"], "indisponible")
        # le LTV doit quand même être calculé avec la dernière valeur connue
        self.assertIn("ltv_actualise", resultat)


if __name__ == "__main__":
    unittest.main()
