import unittest
import json
from pathlib import Path
from unittest.mock import patch

import risk_score_pipeline
from profil_bien_schema import ProfilBien
from risk_scoring_engine import score_profile
from risk_profile_extractor import extract_profil_risque_condense
from schema_profil_risque import CavitesPotentielles


class PipelineTests(unittest.TestCase):
    def test_georisques_uses_rapport_risque_and_not_ppr(self):
        with patch("risk_score_pipeline.get_resultats_rapport_risque", create=True, return_value={"risques": [{"code": "test"}]}) as mock_report:
            with patch("risk_score_pipeline._get_georisques", return_value=[]):
                result = risk_score_pipeline.get_risques_georisques(47.21497, -1.55150, "44109")

        self.assertIn("rapport_risque", result)
        self.assertNotIn("ppr", result)
        self.assertEqual(result["rapport_risque"], {"risques": [{"code": "test"}]})
        mock_report.assert_called_once_with(47.21497, -1.55150)

    def test_hubeau_hydrometrie_and_rivers_are_stubbed(self):
        result = risk_score_pipeline.get_hubeau_hydrometrie(47.21497, -1.55150)
        self.assertEqual(result["stations_hydrometrie"], [])
        self.assertIn("TODO", result["source_status"])

        quality_result = risk_score_pipeline.get_hubeau_qualite_eaux("44109")
        self.assertEqual(quality_result["qualite_eaux_superficielles"], [])
        self.assertIn("TODO", quality_result["source_status"])

    def test_extract_profil_risque_condense_from_real_payload(self):
        payload_path = Path(__file__).resolve().parents[1] / "risques_adresse.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))

        profile = extract_profil_risque_condense(payload)

        self.assertEqual(profile.adresse, "8 Allée du Port Maillard 44000 Nantes")
        self.assertEqual(profile.proxy_climatique.code, "intermediaire")
        self.assertEqual(profile.proxy_climatique.source, "latitude_band_v1")
        self.assertEqual(profile.rga.libelle_source, "argiles_rga")
        self.assertTrue(profile.rga.present)
        self.assertEqual(profile.zone_sismique.zone_code, "3")
        self.assertEqual(profile.radon.classe_potentiel, "3")
        self.assertTrue(profile.facilites_proches.icpe_present)
        self.assertGreater(profile.facilites_proches.icpe_count, 0)
        self.assertGreater(profile.eaux_souterraines.stations_piezometriques_count, 0)
        self.assertIn("copernicus", profile.donnees_manquantes)
        self.assertIn("drias_meteofrance", profile.donnees_manquantes)
        self.assertGreater(profile.historique_evts.total_evts, 0)
        self.assertGreaterEqual(profile.historique_evts.nb_evt_10ans, 1)
        self.assertIn("inondation", profile.risques_naturels)
        self.assertTrue(profile.risques_naturels["inondation"].present)
        self.assertEqual(profile.risques_naturels["inondation"].libelle_source, "inondation")

    def test_score_profile_with_selected_composed_rules(self):
        payload_path = Path(__file__).resolve().parents[1] / "risques_adresse.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        profile = extract_profil_risque_condense(payload)
        profile.cavites = CavitesPotentielles(present=True, count=1, libelle_source="cavites", disponible=True)

        profil_bien = ProfilBien(
            disponible=True,
            annee_construction=1965,
            type_toiture="tuiles",
            isolation_toiture="faible",
            climatisation=False,
            exposition_solaire="forte",
            installation_electrique_annee=1988,
        )

        score = score_profile(
            profile,
            profil_bien=profil_bien,
            activated_rule_ids={
                "COMPOSE_TOITURE_AGEE_ET_HUMIDITE",
                "COMPOSE_ISOLATION_FAIBLE_ET_HUMIDITE",
                "COMPOSE_PRESENCE_CLIMATISATION_ET_STRESS_THERMIQUE",
                "COMPOSE_INSTALLATION_ELECTRIQUE_ANCIENNE",
            },
        )

        triggered_ids = {rule["rule_id"] for rule in score["triggered_rules"]}
        self.assertIn("RGA_FAIBLE_INFILTRATION", triggered_ids)
        self.assertIn("INONDATION_PRESENT_INFILTRATION", triggered_ids)
        self.assertIn("COMPOSE_TOITURE_AGEE_ET_HUMIDITE", triggered_ids)
        self.assertIn("COMPOSE_ISOLATION_FAIBLE_ET_HUMIDITE", triggered_ids)
        self.assertIn("COMPOSE_PRESENCE_CLIMATISATION_ET_STRESS_THERMIQUE", triggered_ids)
        self.assertIn("COMPOSE_INSTALLATION_ELECTRIQUE_ANCIENNE", triggered_ids)

        self.assertGreater(score["peril_scores"]["infiltration"]["score"], 0)
        self.assertGreater(score["peril_scores"]["thermique"]["score"], 0)
        self.assertEqual(score["confidence"]["level"], "medium")
        self.assertIn("DATA_MISSING_CLIMATE", {note["confidence_id"] for note in score["confidence"]["notes"]})


if __name__ == "__main__":
    unittest.main()
