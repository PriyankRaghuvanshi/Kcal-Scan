from __future__ import annotations

from typing import Any, Dict, List, Tuple

from nutrition_mode import (
    NutritionMode,
    get_place_score_weights,
    is_cut_mode,
    normalize_nutrition_mode,
)
from personalization_profiles import (
    get_goal_adjusted_place_weights,
    normalize_personalization_goal,
    personalization_goal_value,
)
from ranking_modifiers import apply_score_modifiers


HEALTHY_PLACE_SCORING_VERSION = "v3_base_plus_modifier"

# Backward-compatible default weight export.
HEALTHY_PLACE_SCORE_WEIGHTS: Dict[str, float] = get_place_score_weights(NutritionMode.DEFAULT)

# Restaurant score now blends metadata heuristics with menu-health distribution.
# When real menu data exists, menu distribution dominates.
MENU_DISTRIBUTION_SIGNAL_WEIGHTS: Dict[str, float] = {
    "top_3_item_average": 0.28,
    "percent_items_under_600_kcal": 0.18,
    "percent_items_over_30g_protein": 0.17,
    "percent_items_flagged_cut_friendly": 0.13,
    "menu_health_density": 0.12,
    "menu_fit_ratio": 0.12,
}

MENU_DOMINANCE_BY_SOURCE: Dict[str, float] = {
    "real_menu": 0.90,
    "user_scan": 0.86,
    "menu_intelligence_store": 0.84,
    "structured_menu": 0.80,
    "llm_inferred": 0.55,
    "heuristic": 0.32,
}

_REAL_MENU_SOURCES = {
    "real_menu",
    "menu_intelligence_store",
    "structured_menu",
    "scraped_menu",
    "user_scan",
    "website_menu",
    "website_text",
    "review_text",
    "ocr_menu",
}

# Component keyword maps are metadata-based heuristics (not menu-level nutrition facts).
_COMPONENT_KEYWORDS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    # Protein density proxy: cuisines and venue tags that commonly offer lean protein choices.
    "protein_density": {
        "positive": (
            "protein",
            "grill",
            "grilled",
            "bbq",
            "kebab",
            "chicken",
            "fish",
            "seafood",
            "sushi",
            "poke",
            "tofu",
            "paneer",
            "lentil",
            "dal",
            "egg",
        ),
        "negative": (
            "dessert",
            "donut",
            "pastry",
            "bakery",
            "ice_cream",
        ),
    },
    # Calorie control proxy: preparation style and venue type likely to support lower-calorie picks.
    "calorie_control": {
        "positive": (
            "salad",
            "healthy",
            "grill",
            "grilled",
            "steamed",
            "baked",
            "soup",
            "mediterranean",
            "japanese",
            "thai",
            "vegetarian",
            "vegan",
        ),
        "negative": (
            "fried",
            "deep fry",
            "fries",
            "burger",
            "pizza",
            "buffet",
            "dessert",
            "pastry",
            "fast_food",
        ),
    },
    # Satiety proxy: higher protein/fiber and whole-food style cues vs hyper-palatable fast-food cues.
    "satiety": {
        "positive": (
            "protein",
            "salad",
            "bowl",
            "grill",
            "grilled",
            "lentil",
            "bean",
            "dal",
            "tofu",
            "paneer",
            "soup",
        ),
        "negative": (
            "dessert",
            "donut",
            "pizza",
            "burger",
            "pastry",
            "sweet",
            "fried",
            "fries",
        ),
    },
    # Fat-loss friendliness proxy: combined cue for lean-protein + calorie control + low ultra-processed bias.
    "fat_loss_friendliness": {
        "positive": (
            "healthy",
            "protein",
            "salad",
            "grill",
            "grilled",
            "mediterranean",
            "sushi",
            "poke",
            "thai",
            "vegetarian",
            "vegan",
        ),
        "negative": (
            "fried",
            "deep fry",
            "fries",
            "burger",
            "pizza",
            "dessert",
            "donut",
            "milkshake",
            "ice_cream",
        ),
    },
}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _normalize_weights(weights: Dict[str, float]) -> Dict[str, float]:
    total = float(sum(max(0.0, float(v or 0.0)) for v in weights.values()) or 0.0)
    if total <= 0:
        return dict(HEALTHY_PLACE_SCORE_WEIGHTS)
    return {k: max(0.0, float(v or 0.0)) / total for k, v in weights.items()}


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    address = str(payload.get("address") or payload.get("vicinity") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    return " ".join(x for x in [name, address, type_text] if x)


def _component_score(
    place_text: str,
    component: str,
) -> Dict[str, Any]:
    keywords = _COMPONENT_KEYWORDS.get(component, {})
    positive = keywords.get("positive", ())
    negative = keywords.get("negative", ())

    pos_hits = [token for token in positive if token in place_text]
    neg_hits = [token for token in negative if token in place_text]

    # Neutral prior because Google Places usually lacks menu-level nutrition values.
    score_0_to_1 = 0.5
    score_0_to_1 += min(0.35, 0.10 * len(pos_hits))
    score_0_to_1 -= min(0.35, 0.10 * len(neg_hits))
    score_0_to_1 = _clamp(score_0_to_1, 0.05, 0.95)

    note: str
    if pos_hits and not neg_hits:
        note = "Positive venue metadata cues for this component."
    elif neg_hits and not pos_hits:
        note = "Negative venue metadata cues for this component."
    elif pos_hits and neg_hits:
        note = "Mixed cues; score is intentionally conservative."
    else:
        note = "No strong cues in venue metadata; neutral fallback used."

    return {
        "score": round(score_0_to_1 * 10.0, 1),
        "positive_signals": pos_hits[:4],
        "negative_signals": neg_hits[:4],
        "note": note,
        "estimated": True,
    }


def _default_breakdown(weights: Dict[str, float]) -> Dict[str, Dict[str, Any]]:
    return {
        component: {
            "score": 5.0,
            "weight": round(float(weights.get(component, 0.0)), 3),
            "positive_signals": [],
            "negative_signals": [],
            "note": "No venue metadata available; neutral fallback used.",
            "estimated": True,
        }
        for component in HEALTHY_PLACE_SCORE_WEIGHTS.keys()
    }


def _normalize_menu_source(source: Any) -> str:
    token = str(source or "").strip().lower()
    if token == "user_scan":
        return "user_scan"
    if token in _REAL_MENU_SOURCES:
        return "real_menu"
    if token in {"llm_inferred", "llm"}:
        return "llm_inferred"
    if token in {"structured_menu"}:
        return "structured_menu"
    if token in {"menu_intelligence_store"}:
        return "menu_intelligence_store"
    return "heuristic"


def _extract_menu_items(place: Dict[str, Any], menu_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    direct_menu = menu_payload if isinstance(menu_payload, dict) else {}
    place_payload = place if isinstance(place, dict) else {}
    candidates: List[Any] = []

    for source in (direct_menu, place_payload):
        if not isinstance(source, dict):
            continue
        value = source.get("top_menu_items")
        if isinstance(value, list) and value:
            candidates = value
            break

    if not candidates:
        for source in (direct_menu, place_payload):
            if not isinstance(source, dict):
                continue
            value = source.get("best_menu_items")
            if isinstance(value, list) and value:
                candidates = value
                break

    if not candidates:
        top = (
            direct_menu.get("top_menu_item")
            if isinstance(direct_menu.get("top_menu_item"), dict)
            else place_payload.get("top_menu_item")
        )
        if isinstance(top, dict):
            candidates = [top]

    out: List[Dict[str, Any]] = []
    for row in candidates:
        if isinstance(row, dict):
            out.append(row)
    return out


def _score_menu_distribution(menu_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not menu_items:
        return {
            "available": False,
            "menu_items_count": 0,
            "top_item_score": 0.0,
            "top_3_item_average": 0.0,
            "percent_items_under_600_kcal": 0.0,
            "percent_items_over_30g_protein": 0.0,
            "percent_items_flagged_cut_friendly": 0.0,
            "menu_health_density": 0.0,
            "healthy_item_count": 0,
            "sub_600_kcal_item_count": 0,
            "protein_25g_plus_item_count": 0,
            "menu_fit_ratio": 0.0,
            "menu_distribution_score": 0.0,
        }

    rows: List[Dict[str, Any]] = [row for row in menu_items if isinstance(row, dict)]
    if not rows:
        return {
            "available": False,
            "menu_items_count": 0,
            "top_item_score": 0.0,
            "top_3_item_average": 0.0,
            "percent_items_under_600_kcal": 0.0,
            "percent_items_over_30g_protein": 0.0,
            "percent_items_flagged_cut_friendly": 0.0,
            "menu_health_density": 0.0,
            "healthy_item_count": 0,
            "sub_600_kcal_item_count": 0,
            "protein_25g_plus_item_count": 0,
            "menu_fit_ratio": 0.0,
            "menu_distribution_score": 0.0,
        }

    item_scores = [
        float(
            _clamp(
                _safe_float(
                    row.get("rank_adjusted_item_score"),
                    _safe_float(row.get("item_score"), 0.0),
                ),
                0.0,
                100.0,
            )
        )
        for row in rows
    ]
    top_scores = sorted(item_scores, reverse=True)[:3]
    top_item_score = top_scores[0] if top_scores else 0.0
    top_3_item_average = sum(top_scores) / max(1, len(top_scores))

    under_600 = 0
    over_30_protein = 0
    protein_25_plus = 0
    cut_friendly = 0
    density_hits = 0
    healthy_item_count = 0

    for row in rows:
        calories = float(_safe_float(row.get("estimated_calories"), 0.0))
        protein = float(_safe_float(row.get("estimated_protein_g"), 0.0))
        score = float(
            _clamp(
                _safe_float(row.get("rank_adjusted_item_score"), _safe_float(row.get("item_score"), 0.0)),
                0.0,
                100.0,
            )
        )
        if calories > 0 and calories <= 600:
            under_600 += 1
        if protein >= 30:
            over_30_protein += 1
        if protein >= 25:
            protein_25_plus += 1
        if bool(row.get("cut_friendly")) or bool(row.get("fat_loss_friendly")):
            cut_friendly += 1
        if score >= 70 and protein >= 28 and (calories <= 650 or calories <= 0):
            density_hits += 1
        if score >= 68 and protein >= 25 and (calories <= 650 or calories <= 0):
            healthy_item_count += 1

    total = max(1, len(rows))
    percent_items_under_600_kcal = (under_600 / total) * 100.0
    percent_items_over_30g_protein = (over_30_protein / total) * 100.0
    percent_items_flagged_cut_friendly = (cut_friendly / total) * 100.0
    menu_health_density = (density_hits / total) * 100.0
    menu_fit_ratio = (healthy_item_count / total) * 100.0

    weighted = (
        top_3_item_average * MENU_DISTRIBUTION_SIGNAL_WEIGHTS["top_3_item_average"]
        + percent_items_under_600_kcal * MENU_DISTRIBUTION_SIGNAL_WEIGHTS["percent_items_under_600_kcal"]
        + percent_items_over_30g_protein * MENU_DISTRIBUTION_SIGNAL_WEIGHTS["percent_items_over_30g_protein"]
        + percent_items_flagged_cut_friendly * MENU_DISTRIBUTION_SIGNAL_WEIGHTS["percent_items_flagged_cut_friendly"]
        + menu_health_density * MENU_DISTRIBUTION_SIGNAL_WEIGHTS["menu_health_density"]
        + menu_fit_ratio * MENU_DISTRIBUTION_SIGNAL_WEIGHTS["menu_fit_ratio"]
    )

    return {
        "available": True,
        "menu_items_count": len(rows),
        "top_item_score": round(top_item_score, 1),
        "top_3_item_average": round(top_3_item_average, 1),
        "percent_items_under_600_kcal": round(percent_items_under_600_kcal, 1),
        "percent_items_over_30g_protein": round(percent_items_over_30g_protein, 1),
        "percent_items_flagged_cut_friendly": round(percent_items_flagged_cut_friendly, 1),
        "menu_health_density": round(menu_health_density, 1),
        "healthy_item_count": int(healthy_item_count),
        "sub_600_kcal_item_count": int(under_600),
        "protein_25g_plus_item_count": int(protein_25_plus),
        "menu_fit_ratio": round(menu_fit_ratio, 1),
        "menu_distribution_score": round(_clamp(weighted, 0.0, 100.0), 1),
    }


def best_options_for_place(place: Dict[str, Any]) -> List[str]:
    text = _place_text(place)
    if any(token in text for token in ("dessert", "pastry", "patisserie", "bakery", "cake", "sweet")):
        return ["Needs menu check: pick lighter savory options", "Prefer less sugary or less fried picks"]
    if any(token in text for token in ("south indian", "idli", "dosa", "udupi", "temple", "canteen")):
        return ["Idli or plain dosa-style option", "Prefer simpler less-oily meals"]
    if any(token in text for token in ("indian", "biryani", "curry", "tandoori", "dal", "paneer")):
        return ["Tandoori or grilled style option", "Dal + salad + controlled roti"]
    if any(token in text for token in ("salad", "healthy", "vegan", "vegetarian")):
        return ["Protein salad", "Veggie + lean meal option"]
    if any(token in text for token in ("sushi", "japanese")):
        return ["Sashimi + miso soup", "Rice portion-controlled poke"]
    if any(token in text for token in ("grill", "bbq", "kebab")):
        return ["Grilled lean item + greens", "Protein + veggie combo"]
    return ["Suggested lighter option", "Needs menu check"]


def score_healthy_place(
    place: Dict[str, Any],
    weights: Dict[str, float] | None = None,
    mode: NutritionMode | str = NutritionMode.DEFAULT,
    personalization_goal: Any = None,
    menu_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = place if isinstance(place, dict) else {}
    menu_ctx = menu_payload if isinstance(menu_payload, dict) else {}
    resolved_mode = normalize_nutrition_mode(mode)
    resolved_goal = normalize_personalization_goal(personalization_goal)
    goal_value = personalization_goal_value(resolved_goal)
    cut_mode_active = is_cut_mode(resolved_mode)
    base_weights = get_place_score_weights(resolved_mode)
    if resolved_goal:
        base_weights = get_goal_adjusted_place_weights(base_weights, resolved_goal)
    applied_weights = _normalize_weights(weights or base_weights)
    place_text = _place_text(payload)

    if not place_text:
        breakdown = _default_breakdown(applied_weights)
        base_venue_score = 5.0
    else:
        breakdown = {}
        weighted_sum = 0.0
        for component in HEALTHY_PLACE_SCORE_WEIGHTS.keys():
            comp = _component_score(place_text, component)
            comp_weight = float(applied_weights.get(component, 0.0) or 0.0)
            comp["weight"] = round(comp_weight, 3)
            breakdown[component] = comp
            weighted_sum += (float(comp["score"]) / 10.0) * comp_weight
        base_venue_score = round(_clamp(weighted_sum * 10.0, 1.0, 10.0), 1)

    menu_items = _extract_menu_items(payload, menu_ctx)
    menu_signals = _score_menu_distribution(menu_items)
    menu_source = _normalize_menu_source(
        menu_ctx.get("menu_source_resolved")
        or menu_ctx.get("menu_items_source_resolved")
        or menu_ctx.get("menu_source")
        or menu_ctx.get("menu_items_source")
        or payload.get("menu_source")
        or payload.get("menu_items_source")
    )
    top_menu_item = (
        menu_ctx.get("top_menu_item")
        if isinstance(menu_ctx.get("top_menu_item"), dict)
        else payload.get("top_menu_item")
        if isinstance(payload.get("top_menu_item"), dict)
        else {}
    )
    top_source = _normalize_menu_source(
        (top_menu_item or {}).get("menu_item_source")
        or (top_menu_item or {}).get("menu_source")
    )
    if top_source in {"real_menu", "user_scan"}:
        menu_source = top_source
    top_item_conf = 0.0
    if menu_items:
        top_item_conf = _safe_float(
            menu_items[0].get("menu_item_confidence"),
            _safe_float(menu_items[0].get("menu_confidence"), _safe_float(menu_items[0].get("confidence"), 0.0)),
        )
    menu_confidence = _clamp(
        _safe_float(menu_ctx.get("menu_confidence"), top_item_conf),
        0.0,
        1.0,
    )

    menu_dominance = 0.0
    menu_distribution_score_100 = 0.0
    if bool(menu_signals.get("available")):
        menu_distribution_score_100 = float(_safe_float(menu_signals.get("menu_distribution_score"), 0.0))
        menu_dominance = float(MENU_DOMINANCE_BY_SOURCE.get(menu_source, MENU_DOMINANCE_BY_SOURCE["heuristic"]))
        if int(_safe_float(menu_signals.get("menu_items_count"), 0.0)) < 3:
            menu_dominance *= 0.82
        if menu_confidence > 0:
            menu_dominance *= _clamp(0.70 + (menu_confidence * 0.50), 0.55, 1.15)
        menu_dominance = _clamp(menu_dominance, 0.18, 0.93)

    blended_score_100 = (base_venue_score * 10.0)
    if menu_dominance > 0:
        blended_score_100 = (base_venue_score * 10.0 * (1.0 - menu_dominance)) + (menu_distribution_score_100 * menu_dominance)
    base_score_100 = _clamp(blended_score_100, 0.0, 100.0)
    modifier_payload = dict(payload)
    if isinstance(menu_ctx, dict):
        modifier_payload.update(menu_ctx)
    modifier_payload["top_menu_item"] = top_menu_item if isinstance(top_menu_item, dict) else {}
    modifier_payload["menu_source_resolved"] = menu_source
    modifier_payload["menu_confidence"] = menu_confidence
    modifier_payload["menu_health_signals"] = {
        "menu_fit_ratio": menu_signals.get("menu_fit_ratio", 0.0),
        "menu_health_density": menu_signals.get("menu_health_density", 0.0),
    }
    modifier_result = apply_score_modifiers(
        base_score=base_score_100,
        payload=modifier_payload,
        context={
            "score_channel": "healthy_place_scoring",
            "goal": goal_value,
            "cut_mode": bool(cut_mode_active),
            "modifier_rollout_phase": str(
                menu_ctx.get("modifier_rollout_phase")
                or payload.get("modifier_rollout_phase")
                or ""
            ).strip(),
        },
    )
    final_score_100 = _clamp(
        _safe_float(modifier_result.get("final_score"), base_score_100),
        0.0,
        100.0,
    )
    health_score = round(_clamp(final_score_100 / 10.0, 1.0, 10.0), 1)
    base_health_score = round(_clamp(base_score_100 / 10.0, 1.0, 10.0), 1)

    badges: List[str] = []
    if bool(menu_signals.get("available")):
        if float(_safe_float(menu_signals.get("top_3_item_average"), 0.0)) >= 76.0:
            badges.append("Strong healthy meals")
        if float(_safe_float(menu_signals.get("percent_items_over_30g_protein"), 0.0)) >= 45.0:
            badges.append("High-protein menu density")
        if float(_safe_float(menu_signals.get("percent_items_under_600_kcal"), 0.0)) >= 45.0:
            badges.append("Lower-calorie options")
        if float(_safe_float(menu_signals.get("percent_items_flagged_cut_friendly"), 0.0)) >= 35.0:
            badges.append("Cut-friendly picks")
    else:
        if breakdown["protein_density"]["score"] >= 7.0:
            badges.append("High-protein options likely")
        if breakdown["calorie_control"]["score"] >= 7.0:
            badges.append("Calorie-control friendly")
        if breakdown["satiety"]["score"] >= 7.0:
            badges.append("Satiety-friendly picks")
        if breakdown["fat_loss_friendliness"]["score"] >= 7.0:
            badges.append("Fat-loss friendly")
    if not badges:
        badges.append("Needs Menu Check")

    if bool(menu_signals.get("available")):
        fat_loss_friendly = bool(
            health_score >= 6.8
            and float(_safe_float(menu_signals.get("menu_health_density"), 0.0)) >= 34.0
            and float(_safe_float(menu_signals.get("top_3_item_average"), 0.0)) >= 70.0
        )
    else:
        fat_loss_friendly = bool(
            health_score >= 6.5 and float(breakdown["fat_loss_friendliness"]["score"]) >= 6.0
        )

    if bool(menu_signals.get("available")):
        cut_friendly = bool(
            cut_mode_active
            and health_score >= 6.9
            and float(_safe_float(menu_signals.get("percent_items_under_600_kcal"), 0.0)) >= 42.0
            and float(_safe_float(menu_signals.get("percent_items_over_30g_protein"), 0.0)) >= 36.0
        )
    else:
        cut_friendly = bool(
            cut_mode_active
            and health_score >= 6.7
            and float(breakdown["calorie_control"]["score"]) >= 6.8
            and float(breakdown["protein_density"]["score"]) >= 6.8
        )

    if cut_mode_active:
        if cut_friendly:
            badges.insert(0, "Cut-friendly short list")
        elif bool(menu_signals.get("available")) and float(_safe_float(menu_signals.get("percent_items_under_600_kcal"), 0.0)) < 32.0:
            badges.append("Calorie-heavy menu mix")
        elif float(breakdown["calorie_control"]["score"]) < 6.0:
            badges.append("Calorie-heavy for cut days")

    cut_warning = ""
    if cut_mode_active and not cut_friendly:
        if bool(menu_signals.get("available")) and float(_safe_float(menu_signals.get("percent_items_under_600_kcal"), 0.0)) < 32.0:
            cut_warning = "Limited lower-calorie meal choices for cut days."
        elif float(breakdown["calorie_control"]["score"]) < 6.0:
            cut_warning = "Watch calories here on cut days."
        elif float(breakdown["protein_density"]["score"]) < 6.0:
            cut_warning = "Protein options may be limited for cut goals."
        else:
            cut_warning = "Moderate fit; portion control still needed."

    breakdown["menu_distribution"] = {
        "score": round(_clamp(menu_distribution_score_100 / 10.0, 0.0, 10.0), 1),
        "weight": round(menu_dominance, 3),
        "signals": {
            "top_item_score": menu_signals.get("top_item_score", 0.0),
            "top_3_item_average": menu_signals.get("top_3_item_average", 0.0),
            "percent_items_under_600_kcal": menu_signals.get("percent_items_under_600_kcal", 0.0),
            "percent_items_over_30g_protein": menu_signals.get("percent_items_over_30g_protein", 0.0),
            "percent_items_flagged_cut_friendly": menu_signals.get("percent_items_flagged_cut_friendly", 0.0),
            "menu_health_density": menu_signals.get("menu_health_density", 0.0),
            "healthy_item_count": menu_signals.get("healthy_item_count", 0),
            "sub_600_kcal_item_count": menu_signals.get("sub_600_kcal_item_count", 0),
            "protein_25g_plus_item_count": menu_signals.get("protein_25g_plus_item_count", 0),
            "menu_fit_ratio": menu_signals.get("menu_fit_ratio", 0.0),
            "menu_items_count": menu_signals.get("menu_items_count", 0),
        },
        "note": (
            "Menu distribution drives this score."
            if bool(menu_signals.get("available"))
            else "Menu unavailable; metadata fallback."
        ),
        "estimated": not bool(menu_signals.get("available")),
    }

    return {
        "health_score": health_score,
        "score_breakdown": breakdown,
        "fat_loss_friendly": fat_loss_friendly,
        "recommended_badges": badges,
        "best_options": best_options_for_place(payload),
        "nutrition_data_available": bool(menu_signals.get("available")),
        "menu_health_signals": {
            "top_item_score": menu_signals.get("top_item_score", 0.0),
            "top_3_item_average": menu_signals.get("top_3_item_average", 0.0),
            "percent_items_under_600_kcal": menu_signals.get("percent_items_under_600_kcal", 0.0),
            "percent_items_over_30g_protein": menu_signals.get("percent_items_over_30g_protein", 0.0),
            "percent_items_flagged_cut_friendly": menu_signals.get("percent_items_flagged_cut_friendly", 0.0),
            "menu_health_density": menu_signals.get("menu_health_density", 0.0),
            "healthy_item_count": menu_signals.get("healthy_item_count", 0),
            "sub_600_kcal_item_count": menu_signals.get("sub_600_kcal_item_count", 0),
            "protein_25g_plus_item_count": menu_signals.get("protein_25g_plus_item_count", 0),
            "menu_fit_ratio": menu_signals.get("menu_fit_ratio", 0.0),
            "menu_items_count": menu_signals.get("menu_items_count", 0),
        },
        "top_item_score": menu_signals.get("top_item_score", 0.0),
        "healthy_item_count": menu_signals.get("healthy_item_count", 0),
        "sub_600_kcal_item_count": menu_signals.get("sub_600_kcal_item_count", 0),
        "protein_25g_plus_item_count": menu_signals.get("protein_25g_plus_item_count", 0),
        "menu_fit_ratio": menu_signals.get("menu_fit_ratio", 0.0),
        "menu_distribution_score": round(_clamp(menu_distribution_score_100 / 10.0, 0.0, 10.0), 1),
        "menu_dominance": round(menu_dominance, 3),
        "menu_source": menu_source,
        "menu_confidence": round(menu_confidence, 2),
        "base_venue_score": round(base_venue_score, 1),
        "base_health_score": base_health_score,
        "base_score": round(_clamp(_safe_float(modifier_result.get("base_score"), base_score_100), 0.0, 100.0), 2),
        "modifier_score_raw": round(_safe_float(modifier_result.get("modifier_score_raw"), 0.0), 2),
        "modifier_score": round(_safe_float(modifier_result.get("modifier_score"), 0.0), 2),
        "final_score": round(final_score_100, 2),
        "score_adjustment_factor": round(_safe_float(modifier_result.get("score_adjustment_factor"), 1.0), 4),
        "modifier_rollout_phase": str(modifier_result.get("modifier_rollout_phase") or "phase_1"),
        "modifier_version": str(modifier_result.get("modifier_version") or "v1"),
        "modifier_breakdown": (
            modifier_result.get("modifier_breakdown")
            if isinstance(modifier_result.get("modifier_breakdown"), dict)
            else {}
        ),
        "scoring_version": HEALTHY_PLACE_SCORING_VERSION,
        "cut_mode_active": cut_mode_active,
        "cut_friendly": cut_friendly,
        "cut_warning": cut_warning,
        "personalization_goal": goal_value,
    }
