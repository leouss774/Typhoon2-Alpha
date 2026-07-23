import json
import unittest
from pathlib import Path

from final_output_assembler import assemble_final_analysis_output
from mistral_analyst import build_mistral_response_schema
from profil_bien_schema import ProfilBien
from risk_profile_extractor import extract_profil_risque_condense
from risk_scoring_engine import load_scoring_rules, score_profile


class FinalOutputAssemblerTests(unittest.TestCase):
    def setUp(self):
        payload_path = Path(__file__).resolve().parents[1] / "risques_adresse.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.profile = extract_profil_risque_condense(payload)
        self.profil_bien = ProfilBien(
            disponible=True,
            annee_construction=1965,
            type_toiture="tuiles",
            isolation_toiture="faible",
            climatisation=False,
            exposition_solaire="forte",
            installation_electrique_annee=1988,
        )
        self.scoring = score_profile(
            self.profile,
            profil_bien=self.profil_bien,
            activated_rule_ids={
                "COMPOSE_TOITURE_AGEE_ET_HUMIDITE",
                "COMPOSE_ISOLATION_FAIBLE_ET_HUMIDITE",
                "COMPOSE_PRESENCE_CLIMATISATION_ET_STRESS_THERMIQUE",
                "COMPOSE_INSTALLATION_ELECTRIQUE_ANCIENNE",
            },
        )

    def test_assemble_final_output_with_mistral_selection(self):
        mistral_selection = {
            "activated_rule_ids": ["COMPOSE_TOITURE_AGEE_ET_HUMIDITE"],
            "declarative_consistency_status": "warning",
            "declarative_consistency_flags": ["roof_age_mismatch"],
        }

        output = assemble_final_analysis_output(
            self.profile,
            self.scoring,
            mistral_selection=mistral_selection,
            profil_bien=self.profil_bien,
            analysis_id="analysis-test-001",
        )

        self.assertEqual(output["version"], "1.0")
        self.assertEqual(output["analysis_id"], "analysis-test-001")
        self.assertEqual(output["address"]["adresse"], "8 Allée du Port Maillard 44000 Nantes")
        self.assertEqual(output["score"]["global"], self.scoring["global_score"])
        self.assertEqual(output["score"]["global_raw"], self.scoring["global_score_raw"])
        self.assertIn("infiltration", output["score"]["perils"])
        self.assertIn("rules", output)
        self.assertIn("traceability", output)
        self.assertEqual(output["mistral"]["declarative_consistency_status"], "warning")
        self.assertEqual(output["mistral"]["activated_rule_ids"], ["COMPOSE_TOITURE_AGEE_ET_HUMIDITE"])
        self.assertTrue(output["traceability"]["mistral_used"])
        self.assertIn("triggered", output["rules"])
        self.assertGreater(len(output["rules"]["triggered"]), 0)

    def test_assemble_final_output_without_mistral_selection(self):
        output = assemble_final_analysis_output(self.profile, self.scoring)
        self.assertEqual(output["mistral"]["declarative_consistency_status"], "unknown")
        self.assertEqual(output["mistral"]["activated_rule_ids"], [])
        self.assertFalse(output["traceability"]["mistral_used"])


if __name__ == "__main__":
    unittest.main()
