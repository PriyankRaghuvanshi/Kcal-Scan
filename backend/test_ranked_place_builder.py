"""
Tests for canonical ranking builder: consistency, flat/sectioned sort trust,
current_place no hidden bump, processed-meal penalty, generic fallback label.
"""
from __future__ import annotations

import unittest

from healthy_food_map import build_sections, enrich_places_for_healthy_map
from ranked_place_builder import build_ranked_place_profile


def _place(
    name: str,
    recommended_order: str,
    estimated_calories: int = 520,
    estimated_protein_g: int = 35,
    menu_item_source: str = "heuristic",
    menu_item_confidence: float = 0.7,
    section: str = "Decent nearby options",
    display_rank_score_100: int = 65,
    distance_meters: int = 200,
    **kwargs,
) -> dict:
    d = {
        "name": name,
        "recommended_order": recommended_order,
        "estimated_calories": estimated_calories,
        "estimated_protein_g": estimated_protein_g,
        "menu_item_source": menu_item_source,
        "menu_item_confidence": menu_item_confidence,
        "section": section,
        "display_rank_score_100": display_rank_score_100,
        "distance_meters": distance_meters,
    }
    d.update(kwargs)
    return d


class TestCanonicalBuilderConsistency(unittest.TestCase):
    """Same place + user_context => same fields for list, hero, map."""

    def test_builder_returns_all_required_fields(self):
        place = _place("Subway", "Grilled chicken sub", 520, 38, "real_menu", 0.85, display_rank_score_100=78)
        place["decision_today"] = "YES"
        place["fit_for_today"] = True
        place["distance_meters"] = 150
        user_ctx = {
            "remaining_protein_g": 45,
            "cut_mode": True,
            "goal": "fat_loss",
            "fit_today_score_100": 80,
            "calorie_fit_score_100": 85,
            "protein_fit_score_100": 90,
            "overshoot_penalty_100": 0,
        }
        out = build_ranked_place_profile(place, user_ctx)
        required = [
            "display_rank_score_100",
            "meal_fitness_score_100",
            "meal_fitness_score",
            "venue_prior_score_100",
            "eligibility_band",
            "section",
            "recommendation_label",
            "confidence_label",
            "why_this_ranked_here",
            "rank_reason_short",
            "score_breakdown",
            "fit_today_score_100",
            "calorie_fit_score_100",
            "protein_fit_score_100",
            "overshoot_penalty_100",
            "best_item_name",
            "best_item_calories",
            "best_item_protein",
            "best_item_source",
            "best_item_is_generic_fallback",
            "best_item_needs_menu_check",
            "food_quality_score_100",
            "protein_density_score_100",
            "context_bonus_100",
            "context_penalty_100",
            "context_net_100",
            "context_mode",
            "context_reason",
            "context_applied",
            "context_components",
            "chosen_candidate_specificity_tier",
            "specificity_bonus_100",
            "display_sort_score_100",
        ]
        for k in required:
            self.assertIn(k, out, f"missing field: {k}")

    def test_same_input_same_output_list_and_map(self):
        place = _place("Indian", "Tandoori chicken + dal", 600, 42, "llm_inferred", 0.78)
        place["decision_today"] = "YES"
        place["fit_for_today"] = True
        place["health_score"] = 5.8
        user_ctx = {"remaining_protein_g": 40, "cut_mode": True, "goal": "fat_loss"}
        list_out = build_ranked_place_profile(place, user_ctx, for_list=True)
        map_out = build_ranked_place_profile(place, user_ctx, for_map=True)
        self.assertEqual(list_out["display_rank_score_100"], map_out["display_rank_score_100"])
        self.assertEqual(list_out["section"], map_out["section"])
        self.assertEqual(list_out["recommendation_label"], map_out["recommendation_label"])
        self.assertEqual(list_out["confidence_label"], map_out["confidence_label"])


class TestFlatSortTrust(unittest.TestCase):
    """sort_mode=flat_score: list order must exactly match display_rank_score_100 descending."""

    def test_flat_sort_order_matches_score_desc(self):
        places = [
            _place("A", "Grilled chicken", display_rank_score_100=58, distance_meters=400),
            _place("B", "Tandoori plate", display_rank_score_100=90, distance_meters=200),
            _place("C", "Salad bowl", display_rank_score_100=72, distance_meters=100),
        ]
        enriched = enrich_places_for_healthy_map(
            places, origin_lat=28.6, origin_lng=77.2, sort_mode="flat_score"
        )
        scores = [p["display_rank_score_100"] for p in enriched]
        self.assertEqual(scores, [90, 72, 58], "flat mode must order by display_rank_score_100 desc")
        names = [p["name"] for p in enriched]
        self.assertEqual(names, ["B", "C", "A"])


class TestSectionedSortTrust(unittest.TestCase):
    """sort_mode=sectioned: items within each section by display_rank_score_100 desc; section order fixed."""

    def test_sectioned_order_within_section_by_score(self):
        places = [
            _place("Low", "Option", section="Decent nearby options", display_rank_score_100=55, distance_meters=100),
            _place("High", "Option", section="Best fit for your goal", display_rank_score_100=88, distance_meters=200),
            _place("Mid", "Option", section="Best fit for your goal", display_rank_score_100=75, distance_meters=50),
        ]
        enriched = enrich_places_for_healthy_map(
            places, origin_lat=28.6, origin_lng=77.2, sort_mode="sectioned"
        )
        # Section order: Best fit first, then Decent, then Needs menu check
        sections_seen = []
        for p in enriched:
            s = p["section"]
            if not sections_seen or sections_seen[-1] != s:
                sections_seen.append(s)
        best_fit_indices = [i for i, p in enumerate(enriched) if p["section"] == "Best fit for your goal"]
        if len(best_fit_indices) >= 2:
            best_fit_scores = [enriched[i]["display_rank_score_100"] for i in best_fit_indices]
            self.assertEqual(best_fit_scores, sorted(best_fit_scores, reverse=True),
                             "within section: order by display_rank_score_100 desc")

    def test_build_sections_order(self):
        places = [
            _place("N1", "X", section="Needs menu check", display_rank_score_100=50),
            _place("D1", "X", section="Decent nearby options", display_rank_score_100=65),
            _place("B1", "X", section="Best fit for your goal", display_rank_score_100=82),
        ]
        sections = build_sections(places)
        names_order = [s["name"] for s in sections]
        self.assertEqual(names_order[0], "Best fit for your goal")
        self.assertEqual(names_order[1], "Decent nearby options")
        self.assertEqual(names_order[2], "Needs menu check")


class TestCurrentPlaceNoHiddenBump(unittest.TestCase):
    """In flat mode, a lower-score current_place must not outrank a higher-score non-current place."""

    def test_flat_mode_current_place_does_not_outrank_higher_score(self):
        places = [
            _place("Higher", "Grilled plate", display_rank_score_100=85, distance_meters=300),
            _place("Current", "Combo meal", display_rank_score_100=60, distance_meters=50, is_current_place=True),
        ]
        enriched = enrich_places_for_healthy_map(
            places, origin_lat=28.6, origin_lng=77.2, sort_mode="flat_score"
        )
        # Order must be by score desc: 85 first, then 60
        self.assertEqual(enriched[0]["display_rank_score_100"], 85)
        self.assertEqual(enriched[0]["name"], "Higher")
        self.assertEqual(enriched[1]["name"], "Current")
        self.assertEqual(enriched[1].get("is_current_place"), True)


class TestProcessedMealPenalty(unittest.TestCase):
    """CUT: processed combo with similar calories but lower protein/quality ranks below grilled/tandoori. No pizza token."""

    def test_processed_combo_ranks_below_grilled_in_cut(self):
        user_ctx = {
            "cut_mode": True,
            "goal": "fat_loss",
            "remaining_protein_g": 45,
            "fit_today_score_100": 70,
            "calorie_fit_score_100": 75,
            "protein_fit_score_100": 80,
            "overshoot_penalty_100": 0,
        }
        grilled = {
            "name": "Grill House",
            "recommended_order": "Grilled chicken + steamed veg",
            "estimated_calories": 520,
            "estimated_protein_g": 42,
            "menu_item_source": "real_menu",
            "menu_item_confidence": 0.8,
            "distance_meters": 200,
            "cuisine_hint": "grill",
            "decision_today": "YES",
            "fit_for_today": True,
        }
        combo = {
            "name": "Fast Burger",
            "recommended_order": "Burger combo with fries and drink",
            "estimated_calories": 540,
            "estimated_protein_g": 22,
            "menu_item_source": "heuristic",
            "menu_item_confidence": 0.7,
            "distance_meters": 150,
            "cuisine_hint": "burger",
            "decision_today": "YES",
            "fit_for_today": True,
        }
        out_grilled = build_ranked_place_profile(grilled, user_ctx)
        out_combo = build_ranked_place_profile(combo, user_ctx)
        self.assertGreater(
            out_grilled["display_rank_score_100"],
            out_combo["display_rank_score_100"],
            "Grilled higher-protein option must rank above processed combo in CUT (no brand token)",
        )


class TestContextIncludedInDisplayScore(unittest.TestCase):
    """display_rank_score_100 = core + personal + context."""

    def test_context_net_included_in_display_score(self):
        place = {
            "name": "Subway",
            "recommended_order": "Grilled chicken sub",
            "estimated_calories": 520,
            "estimated_protein_g": 38,
            "menu_item_source": "real_menu",
            "menu_item_confidence": 0.85,
            "distance_meters": 150,
            "cuisine_hint": "subway",
            "decision_today": "YES",
            "fit_for_today": True,
        }
        user_ctx = {
            "remaining_protein_g": 45,
            "cut_mode": True,
            "goal": "fat_loss",
            "fit_today_score_100": 80,
            "calorie_fit_score_100": 85,
            "protein_fit_score_100": 90,
            "overshoot_penalty_100": 0,
            "context_info": {
                "context_mode": "post_workout_recovery",
                "context_flags": {"post_workout_recovery": True},
                "remaining_calories": 600,
                "remaining_protein_g": 45,
            },
        }
        out = build_ranked_place_profile(place, user_ctx)
        self.assertIn("context_net_100", out)
        self.assertIn("context_mode", out)
        self.assertIn("context_applied", out)
        self.assertIn("context_components", out)
        core = out["meal_fitness_score_100"]
        personal = out.get("personal_history_net_100") or 0
        context = out.get("context_net_100") or 0
        display = out["display_rank_score_100"]
        expected = min(100, max(0, int(round(core + personal + context))))
        self.assertEqual(display, expected, "display should be core+personal+context clamped")

    def test_no_context_info_yields_zero_context_net(self):
        place = {
            "name": "Cafe",
            "recommended_order": "Egg salad",
            "estimated_calories": 400,
            "estimated_protein_g": 28,
            "menu_item_source": "heuristic",
            "menu_item_confidence": 0.65,
            "distance_meters": 200,
            "cuisine_hint": "cafe",
            "decision_today": "YES",
            "fit_for_today": True,
        }
        user_ctx = {"remaining_protein_g": 30, "cut_mode": False}
        out = build_ranked_place_profile(place, user_ctx)
        self.assertEqual(out.get("context_net_100"), 0)
        self.assertFalse(out.get("context_applied"))


class TestSpecificityAwareRanking(unittest.TestCase):
    """Chain/menu-backed candidates preferred over generic when scores are close."""

    def test_specificity_tier_and_bonus_present(self):
        place = _place("Subway", "6-inch Chicken Sub", menu_item_source="chain_registry", chain_key="subway")
        place["decision_today"] = "YES"
        place["fit_for_today"] = True
        user_ctx = {"remaining_protein_g": 40, "cut_mode": True, "goal": "fat_loss"}
        out = build_ranked_place_profile(place, user_ctx)
        self.assertEqual(out["chosen_candidate_specificity_tier"], "chain_registry")
        self.assertEqual(out["specificity_bonus_100"], 4)
        self.assertAlmostEqual(
            out["display_sort_score_100"],
            out["display_rank_score_100"] + 4,
            delta=1.0,
            msg="display_sort_score should be display_rank + specificity_bonus",
        )

    def test_chain_outranks_generic_when_same_core_score(self):
        """When both have same core score, chain should rank higher due to +4 vs -4."""
        subway = _place("Subway", "6-inch Chicken Sub", menu_item_source="chain_registry", chain_key="subway")
        darbar = _place("Darbar", "Tandoori + dal + roti", menu_item_source="heuristic")
        for p in (subway, darbar):
            p["decision_today"] = "YES"
            p["fit_for_today"] = True
            p["estimated_calories"] = 520
            p["estimated_protein_g"] = 35
            p["distance_meters"] = 200
        user_ctx = {"remaining_protein_g": 40, "cut_mode": True, "goal": "fat_loss"}

        places = [subway, darbar]
        for p in places:
            p.update(build_ranked_place_profile(p, user_ctx))
        enriched = enrich_places_for_healthy_map(
            places, origin_lat=28.6, origin_lng=77.2, sort_mode="flat_score"
        )
        self.assertEqual(enriched[0]["name"], "Subway", "Chain-backed should rank first when scores close")

    def test_generic_gets_negative_bonus(self):
        place = _place("Cafe", "Lighter menu option", menu_item_source="heuristic")
        place["decision_today"] = "YES"
        place["fit_for_today"] = True
        user_ctx = {"remaining_protein_g": 40, "cut_mode": True}
        out = build_ranked_place_profile(place, user_ctx)
        self.assertEqual(out["chosen_candidate_specificity_tier"], "generic_fallback")
        self.assertEqual(out["specificity_bonus_100"], -4)


class TestGenericFallbackLabel(unittest.TestCase):
    """Generic fallback cannot be Best pick, cannot have eligibility_band 3; must be Suggested healthier pick or Needs menu check."""

    def test_generic_fallback_not_best_pick(self):
        place = {
            "name": "Cafe",
            "recommended_order": "Egg + chicken plate",
            "estimated_calories": 430,
            "estimated_protein_g": 30,
            "menu_item_source": "heuristic",
            "menu_item_confidence": 0.65,
            "distance_meters": 200,
            "cuisine_hint": "cafe",
            "decision_today": "YES",
            "fit_for_today": True,
        }
        user_ctx = {"cut_mode": True, "goal": "fat_loss", "remaining_protein_g": 40}
        out = build_ranked_place_profile(place, user_ctx)
        self.assertTrue(out["best_item_is_generic_fallback"])
        self.assertNotEqual(out["recommendation_label"], "Best pick")
        self.assertIn(
            out["recommendation_label"],
            ("Suggested healthier pick", "Needs menu check"),
            "generic fallback must be Suggested healthier pick or Needs menu check",
        )
        self.assertLessEqual(out["eligibility_band"], 2, "generic fallback cannot be band 3")


if __name__ == "__main__":
    unittest.main()
