import json
import unittest
from pathlib import Path

from mistral_analyst import build_mistral_messages, build_mistral_response_schema, build_mistral_system_prompt
from risk_profile_extractor import extract_profil_risque_condense
from risk_scoring_engine import load_scoring_rules
from profil_bien_schema import ProfilBien


class MistralAnalystTests(unittest.TestCase):
    def setUp(self):
        payload_path = Path(__file__).resolve().parents[1] / "risques_adresse.json"
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
        self.profile = extract_profil_risque_condense(payload)
        self.rules_manifest = load_scoring_rules()

    def test_system_prompt_lists_only_composed_rule_ids(self):
        prompt = build_mistral_system_prompt(self.rules_manifest)
        self.assertIn("Tu dois répondre uniquement avec un JSON strict", prompt)
        self.assertIn("COMPOSE_TOITURE_AGEE_ET_HUMIDITE", prompt)
        self.assertIn("COMPOSE_INSTALLATION_ELECTRIQUE_AGEE_ET_CHALEUR", prompt)
        self.assertNotIn("RGA_FAIBLE_INFILTRATION", prompt)

    def test_response_schema_is_restricted_and_enum_based(self):
        response_format = build_mistral_response_schema(self.rules_manifest)
        self.assertEqual(response_format["type"], "json_schema")
        schema = response_format["json_schema"]["schema"]
        self.assertEqual(schema["additionalProperties"], False)
        activated_items = schema["properties"]["activated_rule_ids"]["items"]["enum"]
        self.assertIn("COMPOSE_TOITURE_AGEE_ET_HUMIDITE", activated_items)
        self.assertNotIn("RGA_FAIBLE_INFILTRATION", activated_items)
        self.assertIn("declarative_consistency_status", schema["required"])
        self.assertIn("declarative_consistency_flags", schema["required"])

    def test_messages_embed_context_and_allowed_ids(self):
        profil_bien = ProfilBien(disponible=True, annee_construction=1965, type_toiture="tuiles")
        messages = build_mistral_messages(self.profile, profil_bien, self.rules_manifest)
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[1]["role"], "user")
        self.assertIn("rule_ids_composed_autorises", messages[1]["content"])
        self.assertIn("COMPOSE_TOITURE_AGEE_ET_HUMIDITE", messages[1]["content"])
        self.assertIn("proxy_climatique", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
