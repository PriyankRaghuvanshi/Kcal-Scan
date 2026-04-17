"""
Personal Learning Engine — learns from user's food choices to improve recommendations.

Aggregates patterns from meal_feedback_store and meal_decision_event_store:
- Protein preference (grilled vs fried, high-protein tendency)
- Restaurant affinity (which chains visited most)
- Time-of-day patterns (light breakfast → heavy lunch)
- Macro efficiency preference (protein-dense vs balanced)

Used by healthy_nearby ranking to personalize item ordering per user.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, Optional, List
from collections import Counter

logger = logging.getLogger(__name__)


def build_user_food_profile(
    feedback_events: List[Dict[str, Any]],
    decision_events: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build a learned food preference profile from user's history.
    Returns scoring weights that adjust healthy_nearby ranking.
    """
    profile = {
        "total_meals": 0,
        "favorite_chains": [],
        "protein_preference": "balanced",  # "high_protein" | "balanced" | "low_cal"
        "avg_meal_calories": None,
        "preferred_items": [],
        "avoid_patterns": [],
        "time_patterns": {},
        "chain_visit_counts": {},
        "scoring_adjustments": {},
    }

    if not feedback_events and not decision_events:
        return profile

    # Aggregate chain visits
    chain_counter = Counter()
    item_counter = Counter()
    calories_list = []
    protein_list = []

    for event in (decision_events or []):
        chain_key = str(event.get("chain_key") or "").strip()
        item_name = str(event.get("best_item_name") or event.get("selected_item_name") or "").strip()
        cal = event.get("estimated_calories")
        pro = event.get("estimated_protein_g")

        if chain_key:
            chain_counter[chain_key] += 1
        if item_name:
            item_counter[item_name] += 1
        if cal and float(cal) > 0:
            calories_list.append(float(cal))
        if pro and float(pro) > 0:
            protein_list.append(float(pro))

    for event in (feedback_events or []):
        item_name = str(event.get("best_item_name") or event.get("item_name") or "").strip()
        chain_key = str(event.get("chain_key") or "").strip()
        if chain_key:
            chain_counter[chain_key] += 1
        if item_name:
            item_counter[item_name] += 1

    profile["total_meals"] = len(decision_events or []) + len(feedback_events or [])
    profile["chain_visit_counts"] = dict(chain_counter.most_common(20))
    profile["favorite_chains"] = [k for k, _ in chain_counter.most_common(5)]
    profile["preferred_items"] = [k for k, _ in item_counter.most_common(10)]

    # Determine protein preference
    if protein_list:
        avg_protein = sum(protein_list) / len(protein_list)
        profile["avg_protein_per_meal"] = round(avg_protein, 1)
        if avg_protein >= 35:
            profile["protein_preference"] = "high_protein"
        elif avg_protein <= 15:
            profile["protein_preference"] = "low_cal"
        else:
            profile["protein_preference"] = "balanced"

    if calories_list:
        profile["avg_meal_calories"] = round(sum(calories_list) / len(calories_list))

    # Build scoring adjustments for ranking
    adjustments = {}

    # Boost favorite chains
    for chain in profile["favorite_chains"][:3]:
        adjustments[f"chain_boost::{chain}"] = 0.08  # +8% rank boost

    # Boost protein preference
    if profile["protein_preference"] == "high_protein":
        adjustments["protein_weight_boost"] = 0.15  # weight protein 15% more in scoring
    elif profile["protein_preference"] == "low_cal":
        adjustments["calorie_penalty_boost"] = 0.12  # penalize high-cal items 12% more

    profile["scoring_adjustments"] = adjustments

    return profile


def apply_personal_learning(
    items: List[Dict[str, Any]],
    user_profile: Dict[str, Any],
    remaining_protein_g: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    Re-rank items based on user's learned preferences.
    Items already scored by healthy_nearby — this adjusts the order.
    """
    if not user_profile or not user_profile.get("scoring_adjustments"):
        return items

    adjustments = user_profile.get("scoring_adjustments", {})
    favorite_chains = set(user_profile.get("favorite_chains", []))
    protein_pref = user_profile.get("protein_preference", "balanced")

    scored = []
    for item in items:
        score = float(item.get("display_rank_score_100") or item.get("health_score_100") or 50)
        chain_key = str(item.get("chain_key") or "").strip()

        # Boost favorite chains
        if chain_key in favorite_chains:
            boost = adjustments.get(f"chain_boost::{chain_key}", 0)
            score += score * boost

        # Protein preference adjustment
        protein = float(item.get("best_item_protein") or item.get("estimated_protein_g") or 0)
        if protein_pref == "high_protein" and protein >= 30:
            score += score * adjustments.get("protein_weight_boost", 0)
        elif protein_pref == "low_cal":
            cal = float(item.get("best_item_calories") or item.get("estimated_calories") or 0)
            if cal > 600:
                score -= score * adjustments.get("calorie_penalty_boost", 0)

        scored.append({**item, "_personal_score": round(score, 2)})

    # Sort by personal score (highest first)
    scored.sort(key=lambda x: x.get("_personal_score", 0), reverse=True)
    return scored
