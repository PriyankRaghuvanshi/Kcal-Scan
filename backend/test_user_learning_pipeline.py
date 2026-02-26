import unittest
from unittest.mock import patch

try:
    import main_1702 as appmod
    _IMPORT_ERR = ""
except ModuleNotFoundError as e:
    appmod = None
    _IMPORT_ERR = str(e)


@unittest.skipIf(appmod is None, f"main_1702 dependencies unavailable: {_IMPORT_ERR}")
class UserLearningPipelineTests(unittest.TestCase):
    def test_upsert_user_food_prior_updates_online_means_and_method_flags(self):
        existing = {
            "id": "prior-1",
            "user_id": "user-1",
            "food_key": "paneer",
            "portion_multiplier_mean": 1.0,
            "portion_multiplier_n": 2,
            "oil_tsp_mean": 0.5,
            "oil_tsp_n": 1,
            "oil_by_method": {},
            "always_ask_oil_for_methods": [],
        }
        with patch.object(appmod, "SUPABASE_URL", "x"), patch.object(appmod, "SUPABASE_SERVICE_ROLE_KEY", "y"), patch.object(
            appmod, "_read_user_food_prior", return_value=existing
        ), patch.object(appmod, "_recent_oil_corrections_for_method", return_value=2), patch.object(
            appmod, "_sb_patch_with_column_fallback", return_value={}
        ), patch.object(
            appmod, "_sb_insert_with_column_fallback", return_value={}
        ):
            out = appmod._upsert_user_food_prior(
                "user-1",
                "paneer",
                portion_multiplier=1.5,
                oil_added_tsp=1.5,
                cooking_method="pan_fried",
            )

        self.assertEqual(out["portion_multiplier_n"], 3)
        self.assertAlmostEqual(out["portion_multiplier_mean"], (1.0 * 2.0 + 1.5) / 3.0, places=4)
        self.assertEqual(out["oil_tsp_n"], 2)
        self.assertAlmostEqual(out["oil_tsp_mean"], 1.0, places=4)
        self.assertIn("pan fried", out["always_ask_oil_for_methods"])

    def test_apply_scan_user_priors_sets_clarifying_reason_from_user_prior(self):
        items = [
            {
                "item_id": "i1",
                "name": "paneer",
                "grams": 100,
                "cooking_method": "pan_fried",
                "oil_added_tsp": 0,
                "confidence": 0.9,
            }
        ]
        prior = {
            "portion_multiplier_mean": 1.2,
            "portion_multiplier_n": 4,
            "oil_tsp_mean": 1.4,
            "oil_tsp_n": 4,
            "oil_by_method": {"pan fried": {"mean": 1.4, "n": 4}},
            "always_ask_oil_for_methods": ["pan fried"],
        }
        with patch.object(appmod, "_read_user_food_prior", return_value=prior):
            out_items, used = appmod._apply_scan_user_priors("user-1", items, ["pan fried"])

        self.assertTrue(used["portion_prior_used"])
        self.assertTrue(used["asked_clarifying_question"])
        self.assertEqual(used["asked_clarifying_question_reason"], "user_prior_requires_oil_question")
        self.assertGreater(out_items[0]["grams"], 100)

    def test_feedback_endpoint_returns_contract_shape(self):
        payload = {
            "user_id": "31a49f95-fd24-4ce9-8ed8-bf46496a9475",
            "analysis_id": "0fd100e7-aab1-4b4f-9b5e-7414d3aaf6f1",
            "meal_id": "meal-1",
            "feedback_type": "oil",
            "rating": 4,
            "corrections": {
                "item_name": "paneer",
                "food_key": "paneer",
                "cooking_method": "pan_fried",
                "oil_added_tsp": 1.5,
                "portion_multiplier": 1.1,
            },
        }
        with patch.object(appmod, "SUPABASE_URL", ""), patch.object(appmod, "SUPABASE_SERVICE_ROLE_KEY", ""), patch.object(
            appmod,
            "_upsert_user_food_prior",
            return_value={
                "food_key": "paneer",
                "portion_multiplier_mean": 1.12,
                "oil_tsp_mean": 1.05,
                "always_ask_oil_for_methods": ["pan fried"],
            },
        ):
            out = appmod.coach_memory_feedback(payload=payload)

        self.assertTrue(out.get("ok"))
        self.assertTrue(out.get("priors_updated"))
        self.assertEqual(out.get("updated_food_key"), "paneer")
        self.assertIn("new_priors", out)
        self.assertIn("always_ask_oil_for_methods", out["new_priors"])


if __name__ == "__main__":
    unittest.main()

