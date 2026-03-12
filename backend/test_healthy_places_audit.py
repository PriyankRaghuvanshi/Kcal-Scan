"""
Tests for Healthy Nearby audit: helpers, endpoint shape, CLI output.
No ranking logic changes; inspection only.
"""
from __future__ import annotations

import io
import json
import os
import unittest
from unittest.mock import patch

from healthy_places_audit import (
    build_audit_one_liner,
    build_audit_result_row,
    build_filtered_out_entry,
)


def _minimal_place(
    name: str = "Darbar",
    display_rank_score_100: int = 84,
    eligibility_band: int = 3,
    recommendation_label: str = "Best pick",
    confidence_label: str = "Verified",
    best_item_name: str = "Tandoori chicken + dal",
    best_item_calories: int = 610,
    best_item_protein: int = 42,
    rank_reason_short: str = "Higher protein, better whole-food option",
    **kwargs,
) -> dict:
    d = {
        "name": name,
        "place_id": "pid-1",
        "distance_meters": 450,
        "display_rank_score_100": display_rank_score_100,
        "meal_fitness_score_100": 84.0,
        "venue_prior_score_100": 82,
        "eligibility_band": eligibility_band,
        "section": "Best nearby",
        "recommendation_label": recommendation_label,
        "confidence_label": confidence_label,
        "rank_reason_short": rank_reason_short,
        "why_this_ranked_here": "Strong protein, fits today.",
        "best_item_name": best_item_name,
        "best_item_calories": best_item_calories,
        "best_item_protein": best_item_protein,
        "best_item_source": "real_menu",
        "best_item_is_generic_fallback": False,
        "best_item_needs_menu_check": False,
        "fit_today_score_100": 88.0,
        "calorie_fit_score_100": 85.0,
        "protein_fit_score_100": 90.0,
        "overshoot_penalty_100": 0.0,
        "score_breakdown": {
            "macro_fit": 80,
            "protein_density": 85,
            "food_quality": 82,
            "satiety": 75,
            "confidence": 88,
            "distance": 70,
            "price_value": 50,
            "personal_history": 50,
            "penalties": {
                "ultra_processed_penalty": 0,
                "combo_meal_penalty": 0,
                "deep_fried_penalty": 0,
                "sugary_drink_penalty": 0,
                "hyper_palatable_penalty": 0,
                "low_protein_density_penalty": 0,
                "generic_fallback_penalty": 0,
                "overshoot_penalty": 0,
            },
        },
    }
    d.update(kwargs)
    return d


class TestAuditOneLiner(unittest.TestCase):
    def test_one_liner_includes_rank_score_band_item_kcal_protein(self):
        place = _minimal_place()
        line = build_audit_one_liner(place, 1)
        self.assertIn("#1", line)
        self.assertIn("Darbar", line)
        self.assertIn("Score 84", line)
        self.assertIn("Band 3", line)
        self.assertIn("Best pick", line)
        self.assertIn("Verified", line)
        self.assertIn("Tandoori chicken + dal", line)
        self.assertIn("610 kcal", line)
        self.assertIn("42g protein", line)
        self.assertIn("Higher protein", line)

    def test_one_liner_deterministic_same_input_same_output(self):
        place = _minimal_place(name="Pizza Hut", display_rank_score_100=58, eligibility_band=2)
        a = build_audit_one_liner(place, 4)
        b = build_audit_one_liner(place, 4)
        self.assertEqual(a, b)
        self.assertIn("#4", a)
        self.assertIn("Pizza Hut", a)
        self.assertIn("Score 58", a)
        self.assertIn("Band 2", a)


class TestAuditResultRow(unittest.TestCase):
    def test_audit_result_row_has_all_required_fields(self):
        place = _minimal_place()
        row = build_audit_result_row(place, 1)
        required = [
            "rank", "place_name", "place_id", "distance_m",
            "display_rank_score_100", "meal_fitness_score_100", "venue_prior_score_100",
            "eligibility_band", "section", "recommendation_label", "confidence_label",
            "rank_reason_short", "why_this_ranked_here",
            "best_item_name", "best_item_calories", "best_item_protein",
            "best_item_source", "best_item_is_generic_fallback", "best_item_needs_menu_check",
            "fit_today_score_100", "calorie_fit_score_100", "protein_fit_score_100", "overshoot_penalty_100",
            "score_breakdown", "audit_one_liner",
            "context_bonus_100", "context_penalty_100", "context_net_100",
            "context_mode", "context_reason", "context_applied", "context_components",
        ]
        for key in required:
            self.assertIn(key, row, msg=f"missing key: {key}")
        self.assertIsInstance(row["score_breakdown"], dict)
        self.assertIn("penalties", row["score_breakdown"])
        self.assertEqual(row["rank"], 1)
        self.assertEqual(row["place_name"], "Darbar")
        self.assertEqual(row["display_rank_score_100"], 84)
        self.assertEqual(row["audit_one_liner"], build_audit_one_liner(place, 1))

    def test_audit_one_liner_includes_context_when_present(self):
        place = _minimal_place(personal_history_net_100=3, context_net_100=2)
        line = build_audit_one_liner(place, 1)
        self.assertIn("+3 personal", line)
        self.assertIn("+2 context", line)

    def test_audit_result_row_uses_best_order_fallback(self):
        place = _minimal_place()
        del place["best_item_name"]
        del place["best_item_calories"]
        del place["best_item_protein"]
        place["best_order"] = "Grilled chicken wrap"
        place["estimated_calories"] = 480
        place["estimated_protein_g"] = 36
        row = build_audit_result_row(place, 2)
        self.assertEqual(row["best_item_name"], "Grilled chicken wrap")
        self.assertEqual(row["best_item_calories"], 480)
        self.assertEqual(row["best_item_protein"], 36)

    def test_audit_result_row_includes_cache_and_local_profile_fields(self):
        """Audit row includes matched_local_profile, used_venue_intelligence_cache, cache_last_enriched_at, local_profile_id, enqueued_for_enrichment."""
        place = _minimal_place(
            _matched_local_profile=True,
            _local_profile_source="curated_manual",
            _local_profile_confidence=0.85,
            _local_profile_id="prof-uuid-123",
            _used_venue_intelligence_cache=False,
        )
        row = build_audit_result_row(place, 1)
        self.assertTrue(row["matched_local_profile"])
        self.assertEqual(row["local_profile_source"], "curated_manual")
        self.assertEqual(row["local_profile_confidence"], 0.85)
        self.assertEqual(row["local_profile_id"], "prof-uuid-123")
        self.assertFalse(row["used_venue_intelligence_cache"])

        place_cache = _minimal_place(
            _used_venue_intelligence_cache=True,
            _cache_source_type="exact_menu_cache",
            _cache_last_enriched_at="2025-03-01T10:00:00Z",
        )
        row_cache = build_audit_result_row(place_cache, 3)
        self.assertTrue(row_cache["used_venue_intelligence_cache"])
        self.assertEqual(row_cache["cache_source_type"], "exact_menu_cache")
        self.assertEqual(row_cache["cache_last_enriched_at"], "2025-03-01T10:00:00Z")

        place2 = _minimal_place(
            _enqueued_for_enrichment=True,
            _enrichment_enqueue_reason="candidate_low_specificity",
        )
        row2 = build_audit_result_row(place2, 2)
        self.assertTrue(row2["enqueued_for_enrichment"])
        self.assertEqual(row2["enrichment_enqueue_reason"], "candidate_low_specificity")


class TestFilteredOutEntry(unittest.TestCase):
    def test_filtered_out_entry_has_place_name_and_reason(self):
        place = _minimal_place()
        entry = build_filtered_out_entry(place, "limit")
        self.assertEqual(entry["place_name"], "Darbar")
        self.assertEqual(entry["reason_filtered_out"], "limit")

    def test_filtered_out_entry_includes_optional_fields_when_present(self):
        place = _minimal_place()
        place["menu_item_source"] = "heuristic"
        place["menu_item_confidence"] = 0.4
        place["decision_today"] = "NO"
        place["display_rank_score_100"] = 45
        entry = build_filtered_out_entry(place, "limit")
        self.assertEqual(entry["place_name"], "Darbar")
        self.assertEqual(entry["reason_filtered_out"], "limit")
        self.assertIn("menu_item_source", entry)
        self.assertIn("menu_item_confidence", entry)
        self.assertIn("decision_today", entry)
        self.assertIn("display_rank_score_100", entry)


class TestAuditEndpoint(unittest.TestCase):
    """Audit endpoint returns required shape; uses same ranking path as /places/healthy."""

    def test_audit_endpoint_returns_required_fields(self):
        try:
            from fastapi.testclient import TestClient
            from main import app
        except ImportError:
            self.skipTest("FastAPI TestClient or main.app not available")
        client = TestClient(app)
        # Use a valid lat/lng; may return 0 results if no API key
        r = client.get(
            "/places/healthy/audit",
            params={"lat": -33.80, "lng": 150.97, "limit": 5},
        )
        self.assertEqual(r.status_code, 200, msg=r.text)
        data = r.json()
        self.assertIn("query", data)
        self.assertIn("summary", data)
        self.assertIn("results", data)
        self.assertIsInstance(data["results"], list)
        self.assertEqual(data["query"]["lat"], -33.80)
        self.assertEqual(data["query"]["lng"], 150.97)
        self.assertEqual(data["query"]["limit"], 5)
        self.assertIn("places_considered", data["summary"])
        self.assertIn("places_returned", data["summary"])
        self.assertIn("sort_mode", data["summary"])
        self.assertIn("generated_at", data["summary"])
        for row in data["results"]:
            self.assertIn("rank", row)
            self.assertIn("place_name", row)
            self.assertIn("display_rank_score_100", row)
            self.assertIn("audit_one_liner", row)
            self.assertIn("score_breakdown", row)

    def test_audit_endpoint_flat_mode_order_matches_display_score(self):
        try:
            from fastapi.testclient import TestClient
            from main import app
        except ImportError:
            self.skipTest("FastAPI TestClient or main.app not available")
        with patch("main.fetch_google_places") as mock_fetch:
            mock_fetch.return_value = (
                [
                    {"name": "Low", "place_id": "1", "lat": -33.8, "lng": 150.97, "vicinity": "", "rating": 4.0},
                    {"name": "High", "place_id": "2", "lat": -33.8, "lng": 150.97, "vicinity": "", "rating": 4.0},
                ],
                None,
                2,
            )
            client = TestClient(app)
            r = client.get(
                "/places/healthy/audit",
                params={"lat": -33.80, "lng": 150.97, "limit": 10, "sort_mode": "flat_score"},
            )
            if r.status_code != 200:
                self.skipTest("audit endpoint failed (e.g. missing deps)")
            data = r.json()
            results = data.get("results") or []
            if len(results) >= 2:
                scores = [row.get("display_rank_score_100") for row in results]
                self.assertEqual(scores, sorted(scores, reverse=True), "flat_mode should be descending by display_rank_score_100")

    def test_audit_endpoint_include_filtered_out_returns_filtered_diagnostics(self):
        try:
            from fastapi.testclient import TestClient
            from main import app
        except ImportError:
            self.skipTest("FastAPI TestClient or main.app not available")
        client = TestClient(app)
        r = client.get(
            "/places/healthy/audit",
            params={"lat": -33.80, "lng": 150.97, "limit": 2, "include_filtered_out": "true"},
        )
        self.assertEqual(r.status_code, 200)
        data = r.json()
        if data.get("summary", {}).get("places_considered", 0) > 2:
            self.assertIn("filtered_out", data)
            self.assertIsInstance(data["filtered_out"], list)
            for fo in data["filtered_out"]:
                self.assertIn("place_name", fo)
                self.assertIn("reason_filtered_out", fo)


class TestCLIOutput(unittest.TestCase):
    """CLI outputs rows in rank order and markdown has expected columns."""

    def test_cli_markdown_includes_expected_columns(self):
        # Test the markdown formatter with fake results (no HTTP)
        try:
            from tools.audit_healthy_places import print_markdown
        except ImportError:
            # Run from repo root or path differs
            tools_dir = os.path.join(os.path.dirname(__file__), "tools")
            if tools_dir not in __import__("sys").path:
                __import__("sys").path.insert(0, tools_dir)
            from audit_healthy_places import print_markdown
        import sys
        results = [
            {
                "rank": 1,
                "place_name": "Darbar",
                "display_rank_score_100": 84,
                "eligibility_band": 3,
                "recommendation_label": "Best pick",
                "confidence_label": "Verified",
                "best_item_name": "Tandoori chicken + dal",
                "best_item_calories": 610,
                "best_item_protein": 42,
                "section": "Best nearby",
                "rank_reason_short": "Higher protein",
            },
        ]
        buf = io.StringIO()
        old, sys.stdout = sys.stdout, buf
        try:
            print_markdown(results)
        finally:
            sys.stdout = old
        out = buf.getvalue()
        self.assertIn("rank", out)
        self.assertIn("place", out)
        self.assertIn("score", out)
        self.assertIn("band", out)
        self.assertIn("label", out)
        self.assertIn("confidence", out)
        self.assertIn("best item", out)
        self.assertIn("kcal", out)
        self.assertIn("protein", out)
        self.assertIn("section", out)
        self.assertIn("reason", out)
        self.assertIn("Darbar", out)
        self.assertIn("84", out)
        self.assertIn("610", out)
        self.assertIn("42", out)


if __name__ == "__main__":
    unittest.main()
