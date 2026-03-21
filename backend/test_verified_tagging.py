import json
import os
import tempfile
import unittest

from chain_rollout_registry import clear_chain_rollout_registry_cache
from verified_tagging import compute_verified_tag


class VerifiedTaggingTests(unittest.TestCase):
    def tearDown(self) -> None:
        os.environ.pop("CHAIN_ROLLOUT_REGISTRY_PATH", None)
        clear_chain_rollout_registry_cache()

    def test_global_kill_switch_disables_verified(self):
        with tempfile.TemporaryDirectory() as td:
            reg_path = os.path.join(td, "registry.json")
            with open(reg_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "v1",
                        "settings": {
                            "registry_enabled": True,
                            "verified_tag_release_enabled": False,
                            "verified_tag_canary_percent": 100,
                            "verified_tag_shadow_mode": True,
                            "verified_min_confidence": 0.8,
                            "verified_max_source_age_days": 45,
                        },
                        "chains": [
                            {
                                "chain_key": "mcdonalds",
                                "market": "AU",
                                "status": "stable",
                                "features": {"verified_enabled": True, "verified_shadow_mode": True},
                            }
                        ],
                    },
                    f,
                )
            os.environ["CHAIN_ROLLOUT_REGISTRY_PATH"] = reg_path
            clear_chain_rollout_registry_cache()

            payload = {
                "matched_chain_key": "mcdonalds",
                "country_code": "AU",
                "menu_item_source": "chain_registry",
                "menu_item_confidence": 0.95,
                "best_item_is_generic_fallback": False,
                "chosen_candidate_specificity_tier": "exact_menu_match",
            }
            res = compute_verified_tag(payload)
            self.assertEqual(str(res.get("verified_status")), "disabled")
            self.assertFalse(bool(res.get("is_verified")))

    def test_shadow_mode_blocks_render_even_if_eligible(self):
        with tempfile.TemporaryDirectory() as td:
            reg_path = os.path.join(td, "registry.json")
            with open(reg_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "version": "v1",
                        "settings": {
                            "registry_enabled": True,
                            "verified_tag_release_enabled": True,
                            "verified_tag_canary_percent": 100,
                            "verified_tag_shadow_mode": True,
                            "verified_min_confidence": 0.8,
                            "verified_max_source_age_days": 45,
                        },
                        "chains": [
                            {
                                "chain_key": "mcdonalds",
                                "market": "AU",
                                "status": "stable",
                                "features": {"verified_enabled": True, "verified_shadow_mode": True},
                            }
                        ],
                    },
                    f,
                )
            os.environ["CHAIN_ROLLOUT_REGISTRY_PATH"] = reg_path
            clear_chain_rollout_registry_cache()
            res = compute_verified_tag(
                {
                    "matched_chain_key": "mcdonalds",
                    "country_code": "AU",
                    "menu_item_source": "chain_registry",
                    "menu_item_confidence": 0.95,
                    "best_item_is_generic_fallback": False,
                    "chosen_candidate_specificity_tier": "exact_menu_match",
                    "place_id": "place-123",
                }
            )
            self.assertEqual(str(res.get("verified_status")), "verified")
            self.assertFalse(bool(res.get("is_verified")))
            self.assertIn("shadow_mode", list(res.get("verified_reason_codes") or []))


if __name__ == "__main__":
    unittest.main()
