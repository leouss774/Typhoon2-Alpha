"""
Tests simples de bon fonctionnement (pas de framework externe : unittest stdlib).
Lancer avec : python -m unittest discover tests
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from orchestrator import executer, valider_dossier, charger_json

BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


class TestPipeline(unittest.TestCase):
    def setUp(self):
        self.risque = charger_json(os.path.join(BASE_DIR, "exemple_risque.json"))
        self.recommandations = charger_json(os.path.join(BASE_DIR, "exemple_recommandations.json"))
        self.dossier = charger_json(os.path.join(BASE_DIR, "exemple_dossier.json"))

    def test_pipeline_complet_ne_plante_pas(self):
        resultat = executer(self.risque, self.recommandations, self.dossier)
        self.assertIn("valorisation", resultat)
        self.assertIn("projection", resultat)
        self.assertIn("decision", resultat)
        self.assertIn("plan_de_suivi", resultat)

    def test_decision_dans_les_valeurs_attendues(self):
        resultat = executer(self.risque, self.recommandations, self.dossier)
        self.assertIn(resultat["decision"]["statut"], ["accord", "accord_conditionnel", "refus"])

    def test_dossier_incomplet_leve_une_erreur(self):
        dossier_incomplet = dict(self.dossier)
        dossier_incomplet["valeur_marche_bien"] = None
        with self.assertRaises(ValueError):
            valider_dossier(dossier_incomplet)

    def test_bien_tres_solide_donne_un_accord(self):
        # Bien largement sur-valorisé par rapport à l'emprunt : doit passer en accord
        dossier_favorable = dict(self.dossier)
        dossier_favorable["valeur_marche_bien"] = 900000
        dossier_favorable["montant_emprunte"] = 150000
        resultat = executer(self.risque, self.recommandations, dossier_favorable)
        self.assertEqual(resultat["decision"]["statut"], "accord")

    def test_projection_couvre_toute_la_duree(self):
        resultat = executer(self.risque, self.recommandations, self.dossier)
        self.assertEqual(
            len(resultat["projection"]["scenario_sans_travaux"]),
            self.dossier["duree_annees"] + 1,
        )


if __name__ == "__main__":
    unittest.main()
