import unittest

import main as appmod


class ScanCorrectionRerunTests(unittest.TestCase):
    def test_macro_override_recomputes_totals_and_item_kcal(self):
        results = [
            {"item_id": "i1", "kcal": 300.0, "macros": {"protein_g": 20.0, "carbs_g": 25.0, "fat_g": 10.0}},
            {"item_id": "i2", "kcal": 200.0, "macros": {"protein_g": 10.0, "carbs_g": 20.0, "fat_g": 8.0}},
        ]
        totals = {"kcal": 500.0, "protein_g": 30.0, "carbs_g": 45.0, "fat_g": 18.0}
        micros = {"fiber_g": 10.0, "_units": {"fiber_g": "g"}}
        override = appmod.MacroOverrideEdit(protein_g=40.0, carbs_g=50.0, fat_g=20.0)

        out_results, out_totals, out_micros, correction = appmod._apply_macro_override_to_scan_result(
            results,
            totals,
            micros,
            override,
        )

        self.assertIsInstance(out_results, list)
        self.assertEqual(round(float(out_totals.get("protein_g") or 0.0), 1), 40.0)
        self.assertEqual(round(float(out_totals.get("carbs_g") or 0.0), 1), 50.0)
        self.assertEqual(round(float(out_totals.get("fat_g") or 0.0), 1), 20.0)
        self.assertEqual(round(float(out_totals.get("kcal") or 0.0), 1), 560.0)
        self.assertEqual(round(float(out_totals.get("total_kcal") or 0.0), 1), 560.0)
        self.assertEqual(round(float(correction.get("kcal") or 0.0), 1), 560.0)
        self.assertGreaterEqual(float(out_results[0].get("kcal") or 0.0), 0.0)
        self.assertGreaterEqual(float(out_results[1].get("kcal") or 0.0), 0.0)
        self.assertGreaterEqual(float(out_micros.get("fiber_g") or 0.0), 0.0)

    def test_oatmeal_rule_uses_egg_count_not_protein_add_on(self):
        oatmeal_rule = None
        for r in appmod._CLARIFICATION_RULES:
            pattern = r.get("pattern")
            if pattern and pattern.search("oatmeal"):
                oatmeal_rule = r
                break
        self.assertIsNotNone(oatmeal_rule)
        keys = [str(q.get("key") or "") for q in (oatmeal_rule.get("questions") or []) if isinstance(q, dict)]
        self.assertIn("egg_count", keys)
        self.assertNotIn("protein_add_on", keys)


if __name__ == "__main__":
    unittest.main()
