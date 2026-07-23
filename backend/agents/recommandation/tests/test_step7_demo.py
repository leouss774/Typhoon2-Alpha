import unittest

from step7_demo import run_demo_cases


class Step7DemoTests(unittest.TestCase):
    def test_demo_cases_include_real_and_synthetic_outputs(self):
        result = run_demo_cases()
        self.assertIn("demo_cases", result)
        self.assertEqual(len(result["demo_cases"]), 2)

        real_case, synthetic_case = result["demo_cases"]
        self.assertEqual(real_case["analysis_id"], "step7-real-nantes-no-declarative")
        self.assertEqual(synthetic_case["analysis_id"], "step7-synthetic-declarative-cross-check")
        self.assertFalse(real_case["traceability"]["mistral_used"])
        self.assertTrue(synthetic_case["traceability"]["mistral_used"])
        self.assertEqual(synthetic_case["mistral"]["declarative_consistency_status"], "warning")
        self.assertGreater(synthetic_case["score"]["global"], real_case["score"]["global"])
        self.assertGreater(len(synthetic_case["rules"]["triggered"]), len(real_case["rules"]["triggered"]))


if __name__ == "__main__":
    unittest.main()
