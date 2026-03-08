from __future__ import annotations

from typing import Any, Dict, List

from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import score_healthy_place
from menu_item_scoring import recommend_menu_items_for_place
from nutrition_mode import NutritionMode, normalize_nutrition_mode


NEARBY_FEED_VERSION = "v1"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _normalize_place_card(place: Dict[str, Any], mode: NutritionMode | str = NutritionMode.DEFAULT) -> Dict[str, Any]:
    payload = place if isinstance(place, dict) else {}
    resolved_mode = normalize_nutrition_mode(mode)

    try:
        scoring = score_healthy_place(payload, mode=resolved_mode)
    except Exception:
        scoring = {"health_score": 5.0, "fat_loss_friendly": False, "cut_friendly": False}

    health_score_10pt = round(_clamp(_safe_float(scoring.get("health_score"), 5.0), 1.0, 10.0), 1)

    try:
        order = suggest_best_order_for_place(
            payload,
            health_score=health_score_10pt,
            mode=resolved_mode,
        )
    except Exception:
        order = {}

    try:
        menu = recommend_menu_items_for_place(
            payload,
            health_score=health_score_10pt,
            mode=resolved_mode,
        )
    except Exception:
        menu = {"top_menu_item": None, "menu_item_scoring_available": False}

    top_menu_item = menu.get("top_menu_item") if isinstance(menu.get("top_menu_item"), dict) else {}

    estimated_calories = int(
        _safe_float(top_menu_item.get("estimated_calories"), _safe_float(order.get("estimated_calories"), 520))
        or 520
    )
    estimated_protein_g = int(
        _safe_float(top_menu_item.get("estimated_protein_g"), _safe_float(order.get("estimated_protein_g"), 32))
        or 32
    )

    return {
        "name": str(payload.get("name") or "").strip(),
        "place_id": str(payload.get("place_id") or payload.get("id") or "").strip(),
        "lat": float(_safe_float(payload.get("lat"), 0.0) or 0.0),
        "lng": float(_safe_float(payload.get("lng"), 0.0) or 0.0),
        "address": str(payload.get("address") or payload.get("vicinity") or "").strip(),
        "rating": float(_safe_float(payload.get("rating"), 0.0) or 0.0),
        "health_score": health_score_10pt,
        "best_order": str(top_menu_item.get("item_name") or order.get("best_order") or "Grilled protein bowl"),
        "estimated_calories": max(0, estimated_calories),
        "estimated_protein_g": max(0, estimated_protein_g),
        "estimated_satiety": str(
            top_menu_item.get("estimated_satiety")
            or order.get("estimated_satiety")
            or "medium"
        ),
        "fat_loss_friendly": bool(scoring.get("fat_loss_friendly", False)),
        "cut_friendly": bool(order.get("cut_friendly", scoring.get("cut_friendly", False))),
        "cut_mode_active": bool(order.get("cut_mode_active", resolved_mode == NutritionMode.CUT)),
        "short_reason": str(
            top_menu_item.get("short_reason")
            or order.get("short_reason")
            or "Good fit for smarter eating choices nearby."
        ),
        "menu_item_scoring_available": bool(menu.get("menu_item_scoring_available", False)),
    }


def _section(title: str, places: List[Dict[str, Any]]) -> Dict[str, Any]:
    return {"title": title, "places": places}


def build_healthy_nearby_feed(
    nearby_places: List[Dict[str, Any]],
    limit_per_section: int = 6,
) -> Dict[str, Any]:
    max_items = max(1, min(12, int(_safe_float(limit_per_section, 6) or 6)))

    default_cards: List[Dict[str, Any]] = []
    cut_cards: List[Dict[str, Any]] = []

    for place in (nearby_places or []):
        if not isinstance(place, dict):
            continue
        default_cards.append(_normalize_place_card(place, mode=NutritionMode.DEFAULT))
        cut_cards.append(_normalize_place_card(place, mode=NutritionMode.CUT))

    best_lunch = sorted(
        default_cards,
        key=lambda p: (
            float(_safe_float(p.get("health_score"), 0.0) or 0.0),
            int(_safe_float(p.get("estimated_protein_g"), 0) or 0),
            -int(_safe_float(p.get("estimated_calories"), 999) or 999),
        ),
        reverse=True,
    )[:max_items]

    under_600 = sorted(
        [p for p in default_cards if int(_safe_float(p.get("estimated_calories"), 9999) or 9999) <= 600],
        key=lambda p: (
            float(_safe_float(p.get("health_score"), 0.0) or 0.0),
            int(_safe_float(p.get("estimated_protein_g"), 0) or 0),
            -int(_safe_float(p.get("estimated_calories"), 999) or 999),
        ),
        reverse=True,
    )[:max_items]

    high_protein = sorted(
        [p for p in default_cards if int(_safe_float(p.get("estimated_protein_g"), 0) or 0) >= 30],
        key=lambda p: (
            int(_safe_float(p.get("estimated_protein_g"), 0) or 0),
            float(_safe_float(p.get("health_score"), 0.0) or 0.0),
            -int(_safe_float(p.get("estimated_calories"), 999) or 999),
        ),
        reverse=True,
    )[:max_items]

    cut_mode_best = sorted(
        cut_cards,
        key=lambda p: (
            1 if bool(p.get("cut_friendly")) else 0,
            float(_safe_float(p.get("health_score"), 0.0) or 0.0),
            -int(_safe_float(p.get("estimated_calories"), 999) or 999),
            int(_safe_float(p.get("estimated_protein_g"), 0) or 0),
        ),
        reverse=True,
    )[:max_items]

    return {
        "sections": [
            _section("Best lunch near you", best_lunch),
            _section("Under 600 kcal nearby", under_600),
            _section("High protein meals nearby", high_protein),
            _section("Best options for Cut Mode", cut_mode_best),
        ],
        "feed_version": NEARBY_FEED_VERSION,
    }
