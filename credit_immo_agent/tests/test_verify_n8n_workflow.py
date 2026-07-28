import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from verify_n8n_workflow import verifier

CHEMIN_WORKFLOW = os.path.join(os.path.dirname(__file__), "..", "n8n", "credit_agent_workflow.json")


class TestVerifierWorkflow(unittest.TestCase):
    def test_workflow_fourni_sans_erreur_structurelle(self):
        rapport = verifier(CHEMIN_WORKFLOW, ping_urls=False)
        self.assertFalse(rapport.a_des_erreurs, [r.message for r in rapport.resultats if r.niveau == "erreur"])

    def test_avertissement_dvf_cquest_detecte(self):
        rapport = verifier(CHEMIN_WORKFLOW, ping_urls=False)
        messages = [r.message for r in rapport.resultats]
        self.assertTrue(any("api.cquest.org" in m for m in messages))

    def test_champs_obligatoires_detectes(self):
        rapport = verifier(CHEMIN_WORKFLOW, ping_urls=False)
        messages = " ".join(r.message for r in rapport.resultats)
        self.assertIn("montant_emprunte", messages)
        self.assertIn("duree_annees", messages)


if __name__ == "__main__":
    unittest.main()
