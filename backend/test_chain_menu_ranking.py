"""
Ranking behavior for chain-backed items (Chipotle US, Faasos IN).
Asserts exact_menu_match / ingested_chain_item wins over generic fallback when appropriate.
Uses unittest and menu_item_scoring internals; no real Supabase.
"""
import unittest
from unittest.mock import patch

from nutrition_mode import NutritionMode, normalize_nutrition_mode, is_cut_mode
from menu_item_scoring import (
    score_menu_item,
    _sorted_scored_items,
    SOURCE_PRIORITY_WEIGHTS,
)
from place_trace_debug import get_specificity_bonus_100, TIER_EXACT_MENU_MATCH, TIER_GENERIC_FALLBACK


def _chipotle_high_protein_bowl():
    return {
        "item_name": "High Protein Bowl",
        "estimated_calories": 820,
        "estimated_protein_g": 60,
        "estimated_carbs_g": 55,
        "estimated_fat_g": 35,
        "menu_item_source": "ingested_chain_item",
        "profile_source": "chain_menu_supabase",
        "specificity_tier": "exact_menu_match",
        "confidence": 0.82,
    }


def _chipotle_heavy_burrito():
    return {
        "item_name": "Large Burrito with Queso",
        "estimated_calories": 950,
        "estimated_protein_g": 38,
        "estimated_carbs_g": 85,
        "estimated_fat_g": 42,
        "menu_item_source": "ingested_chain_item",
        "confidence": 0.78,
    }


def _chipotle_salad_bowl():
    return {
        "item_name": "Green Goddess Cobb Salad with Chicken",
        "estimated_calories": 520,
        "estimated_protein_g": 40,
        "estimated_carbs_g": 25,
        "estimated_fat_g": 30,
        "menu_item_source": "ingested_chain_item",
        "confidence": 0.86,
    }


def _generic_mexican_fallback():
    return {
        "item_name": "Lighter menu option",
        "estimated_calories": 520,
        "estimated_protein_g": 28,
        "estimated_carbs_g": 48,
        "estimated_fat_g": 18,
        "menu_item_source": "heuristic",
        "confidence": 0.52,
    }


def _faasos_high_protein_wrap():
    return {
        "item_name": "High Protein Chicken Wrap",
        "estimated_calories": 520,
        "estimated_protein_g": 35,
        "estimated_carbs_g": 40,
        "estimated_fat_g": 20,
        "menu_item_source": "ingested_chain_item",
        "profile_source": "chain_menu_supabase",
        "specificity_tier": "exact_menu_match",
        "confidence": 0.76,
    }


def _faasos_cheese_heavy_wrap():
    return {
        "item_name": "Cheese, Spinach & Corn Wrap",
        "estimated_calories": 540,
        "estimated_protein_g": 18,
        "estimated_carbs_g": 50,
        "estimated_fat_g": 26,
        "menu_item_source": "ingested_chain_item",
        "confidence": 0.72,
    }


def _generic_wrap_fallback():
    return {
        "item_name": "Lean wrap",
        "estimated_calories": 480,
        "estimated_protein_g": 24,
        "estimated_carbs_g": 45,
        "estimated_fat_g": 20,
        "menu_item_source": "heuristic",
        "confidence": 0.52,
    }


def _score_candidates(candidates, place_text="Chipotle", cut_mode=False, goal=None):
    mode = NutritionMode.CUT if cut_mode else NutritionMode.DEFAULT
    context = {
        "place_text": place_text,
        "cuisine_hint": "mexican" if "chipotle" in place_text.lower() else "indian",
        "menu_source": "ingested_chain_item",
        "mode": mode.value,
        "place": {"name": place_text},
        "personalization_goal": goal,
    }
    scored = []
    for c in candidates:
        s = score_menu_item(
            c,
            context=context,
            mode=mode,
            personalization_goal=goal,
            use_llm_copy=False,
        )
        scored.append(s)
    return _sorted_scored_items(scored, mode)


class TestChipotleProteinRescue(unittest.TestCase):
    """Protein rescue: high-protein bowl beats generic Mexican fallback."""

    def test_chipotle_protein_rescue_high_protein_bowl_beats_generic(self):
        candidates = [_generic_mexican_fallback(), _chipotle_high_protein_bowl()]
        sorted_items = _score_candidates(candidates, place_text="Chipotle", cut_mode=True)
        self.assertGreater(len(sorted_items), 0)
        top = sorted_items[0]
        # Pipeline may rewrite "High Protein Bowl" to coarse name for mexican; chain must still win by source.
        self.assertEqual(
            str(top.get("menu_item_source") or "").strip().lower(),
            "ingested_chain_item",
        )
        # Top item should be the high-protein chain item (60g protein), not the generic (28g).
        self.assertGreaterEqual(top.get("estimated_protein_g", 0), 50)


class TestChipotleLighterOption(unittest.TestCase):
    """Lighter option: salad/bowl beats heavier burrito-style."""

    def test_chipotle_lighter_option_salad_beats_heavy_burrito(self):
        candidates = [_chipotle_heavy_burrito(), _chipotle_salad_bowl()]
        sorted_items = _score_candidates(candidates, place_text="Chipotle", cut_mode=True)
        self.assertGreater(len(sorted_items), 0)
        top = sorted_items[0]
        self.assertEqual(top.get("item_name"), "Green Goddess Cobb Salad with Chicken")
        self.assertLess(top.get("estimated_calories", 999), 600)


class TestFaasosProteinRescue(unittest.TestCase):
    """Faasos protein rescue: high-protein wrap beats generic wrap fallback."""

    def test_faasos_protein_rescue_high_protein_wrap_beats_generic(self):
        candidates = [_generic_wrap_fallback(), _faasos_high_protein_wrap()]
        sorted_items = _score_candidates(
            candidates, place_text="Faasos", cut_mode=True
        )
        self.assertGreater(len(sorted_items), 0)
        top = sorted_items[0]
        self.assertEqual(top.get("item_name"), "High Protein Chicken Wrap")
        self.assertEqual(
            str(top.get("menu_item_source") or "").strip().lower(),
            "ingested_chain_item",
        )


class TestFaasosLighterOption(unittest.TestCase):
    """Faasos lighter option: simpler high-protein wrap beats cheese-heavy wrap."""

    def test_faasos_lighter_option_simple_wrap_beats_cheese_heavy(self):
        candidates = [_faasos_cheese_heavy_wrap(), _faasos_high_protein_wrap()]
        sorted_items = _score_candidates(
            candidates, place_text="Faasos", cut_mode=True
        )
        self.assertGreater(len(sorted_items), 0)
        top = sorted_items[0]
        self.assertEqual(top.get("item_name"), "High Protein Chicken Wrap")
        self.assertGreater(top.get("estimated_protein_g", 0), 30)


class TestExactMenuMatchWinsOverGeneric(unittest.TestCase):
    """When scores are close, exact_menu_match wins over generic fallback."""

    def test_source_priority_ingested_higher_than_heuristic(self):
        self.assertGreater(
            SOURCE_PRIORITY_WEIGHTS.get("ingested_chain_item", 0),
            SOURCE_PRIORITY_WEIGHTS.get("heuristic", 0),
        )

    def test_specificity_bonus_exact_higher_than_generic(self):
        exact_bonus = get_specificity_bonus_100(TIER_EXACT_MENU_MATCH)
        generic_bonus = get_specificity_bonus_100(TIER_GENERIC_FALLBACK)
        self.assertGreater(exact_bonus, generic_bonus)

    def test_sorted_order_exact_menu_match_first_when_scores_close(self):
        chain_item = _chipotle_high_protein_bowl()
        generic_item = _generic_mexican_fallback()
        generic_item["estimated_calories"] = 500
        generic_item["estimated_protein_g"] = 30
        candidates = [generic_item, chain_item]
        sorted_items = _score_candidates(candidates, place_text="Chipotle", cut_mode=False)
        self.assertGreater(len(sorted_items), 0)
        top_source = str((sorted_items[0].get("menu_item_source") or "").strip().lower())
        self.assertEqual(top_source, "ingested_chain_item")
