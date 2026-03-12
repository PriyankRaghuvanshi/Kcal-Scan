from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from coach_messages import build_place_coach_message
from ranking_modifiers import apply_score_modifiers
from recommendation_safety import has_strong_menu_evidence, sanitize_recommended_item
from swap_intelligence import build_swap_suggestions


HEALTHY_FOOD_MAP_VERSION = "v1"
LOCAL_RANKING_VERSION = "v3_base_plus_modifier"

DISTANCE_TIER_1_MAX_M = 800
DISTANCE_TIER_2_MAX_M = 1500
DISTANCE_TIER_3_MAX_M = 3000
CURRENT_PLACE_DISTANCE_MAX_M = 100

DISTANCE_BAND_1_MAX_M = 500
DISTANCE_BAND_2_MAX_M = 1000
DISTANCE_BAND_3_MAX_M = 2000
DISTANCE_BAND_4_MAX_M = 3000

SOURCE_RANK_WEIGHTS: Dict[str, float] = {
    "real_menu": 1.00,
    "user_scan": 0.95,
    "llm_inferred": 0.80,
    "heuristic": 0.65,
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _haversine_meters(lat1: Any, lng1: Any, lat2: Any, lng2: Any) -> Optional[int]:
    a1 = _safe_float(lat1, float("nan"))
    o1 = _safe_float(lng1, float("nan"))
    a2 = _safe_float(lat2, float("nan"))
    o2 = _safe_float(lng2, float("nan"))
    if any(math.isnan(v) for v in (a1, o1, a2, o2)):
        return None

    r = 6371000.0
    p1 = math.radians(a1)
    p2 = math.radians(a2)
    dlat = p2 - p1
    dlng = math.radians(o2 - o1)
    aa = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(aa), math.sqrt(1.0 - aa))
    return int(max(0.0, r * c))


def _score_to_100(value: Any) -> int:
    score = _safe_float(value, 0.0)
    if score <= 10.0:
        score *= 10.0
    return int(round(_clamp(score, 0.0, 100.0)))


def _score_band(score_100: int) -> str:
    if int(score_100) >= 80:
        return "high"
    if int(score_100) >= 60:
        return "medium"
    return "low"


def _map_pin_color(score_band: str) -> str:
    band = str(score_band or "").strip().lower()
    if band == "high":
        return "green"
    if band == "medium":
        return "yellow"
    return "red"


def _map_pin_hex(score_band: str) -> str:
    band = str(score_band or "").strip().lower()
    if band == "high":
        return "#22c55e"
    if band == "medium":
        return "#f59e0b"
    return "#ef4444"


def _distance_tier(distance_meters: int) -> str:
    dm = int(max(0, _safe_int(distance_meters, 0)))
    if dm <= DISTANCE_TIER_1_MAX_M:
        return "tier_1"
    if dm <= DISTANCE_TIER_2_MAX_M:
        return "tier_2"
    if dm <= DISTANCE_TIER_3_MAX_M:
        return "tier_3"
    return "tier_4"


def _distance_band(distance_meters: int) -> str:
    dm = int(max(0, _safe_int(distance_meters, 0)))
    if dm <= DISTANCE_BAND_1_MAX_M:
        return "0_to_500m"
    if dm <= DISTANCE_BAND_2_MAX_M:
        return "500m_to_1km"
    if dm <= DISTANCE_BAND_3_MAX_M:
        return "1km_to_2km"
    if dm <= DISTANCE_BAND_4_MAX_M:
        return "2km_to_3km"
    return "over_3km"


def _is_current_place(distance_meters: int) -> bool:
    return bool(int(max(0, _safe_int(distance_meters, 0))) <= CURRENT_PLACE_DISTANCE_MAX_M)


def _distance_tier_index(distance_tier: str) -> int:
    token = str(distance_tier or "").strip().lower()
    if token == "tier_1":
        return 1
    if token == "tier_2":
        return 2
    if token == "tier_3":
        return 3
    return 4


def _distance_weight(distance_meters: int) -> float:
    dm = float(max(0, _safe_int(distance_meters, 0)))
    if dm <= DISTANCE_BAND_1_MAX_M:
        # 0-500m: best practical walking distance.
        return _clamp(1.0 - ((dm / float(DISTANCE_BAND_1_MAX_M)) * 0.16), 0.84, 1.0)
    if dm <= DISTANCE_BAND_2_MAX_M:
        # 500m-1km: still practical but clearly weaker than very close options.
        ratio = (dm - DISTANCE_BAND_1_MAX_M) / float(DISTANCE_BAND_2_MAX_M - DISTANCE_BAND_1_MAX_M)
        return _clamp(0.84 - (ratio * 0.16), 0.68, 0.84)
    if dm <= DISTANCE_BAND_3_MAX_M:
        # 1km-2km: available but heavily penalized for convenience.
        ratio = (dm - DISTANCE_BAND_2_MAX_M) / float(DISTANCE_BAND_3_MAX_M - DISTANCE_BAND_2_MAX_M)
        return _clamp(0.68 - (ratio * 0.24), 0.44, 0.68)
    if dm <= DISTANCE_BAND_4_MAX_M:
        # 2km-3km: weak local relevance unless quality is clearly superior.
        ratio = (dm - DISTANCE_BAND_3_MAX_M) / float(DISTANCE_BAND_4_MAX_M - DISTANCE_BAND_3_MAX_M)
        return _clamp(0.44 - (ratio * 0.18), 0.26, 0.44)
    # Beyond 3km: keep as long-tail alternatives only.
    tail = min(1.0, (dm - DISTANCE_BAND_4_MAX_M) / 2000.0)
    return _clamp(0.26 - (tail * 0.14), 0.10, 0.26)


def _fit_for_today(payload: Dict[str, Any]) -> Optional[bool]:
    if isinstance(payload.get("fit_for_today"), bool):
        return bool(payload.get("fit_for_today"))

    token = str(payload.get("decision_today") or "").strip().upper()
    if token == "YES":
        return True
    if token == "NO":
        return False
    return None


def _decision_token(payload: Dict[str, Any], fit_for_today: Optional[bool]) -> str:
    token = str(payload.get("decision_today") or "").strip().upper()
    if token in {"YES", "MAYBE", "NO"}:
        return token
    if fit_for_today is True:
        return "YES"
    if fit_for_today is False:
        return "NO"
    return "MAYBE"


def _fit_for_today_score(payload: Dict[str, Any], fit_for_today: Optional[bool]) -> float:
    token = _decision_token(payload, fit_for_today)
    score = 56.0
    if token == "YES":
        score = 100.0
    elif token == "NO":
        score = 20.0

    if payload.get("fits_remaining_calories") is False:
        score -= 12.0
    if payload.get("fits_remaining_protein") is False:
        score -= 8.0
    return _clamp(score, 0.0, 100.0)


def _top_item_score(payload: Dict[str, Any]) -> float:
    top = payload.get("top_menu_item") if isinstance(payload.get("top_menu_item"), dict) else {}
    direct = _safe_float(top.get("item_score"), -1.0)
    if direct >= 0.0:
        return _clamp(direct, 0.0, 100.0)

    menu_distribution = _safe_float(payload.get("menu_distribution_score"), -1.0)
    if menu_distribution >= 0.0:
        return _clamp(menu_distribution * 10.0, 0.0, 100.0)

    return _clamp(_score_to_100(payload.get("health_score")), 0.0, 100.0)


def _restaurant_health_score(payload: Dict[str, Any], goal: str) -> float:
    has_goal = bool(str(goal or "").strip())
    preferred = payload.get("personalized_health_score") if has_goal else None
    if preferred is not None:
        return _clamp(_score_to_100(preferred), 0.0, 100.0)
    return _clamp(_score_to_100(payload.get("health_score")), 0.0, 100.0)


def _goal_relevance_score(
    payload: Dict[str, Any],
    *,
    goal: str,
    cut_mode: bool,
    restaurant_health_score: float,
) -> float:
    score = float(restaurant_health_score)
    goal_token = str(goal or payload.get("personalization_goal") or "").strip().lower()

    if payload.get("personalized_health_score") is not None:
        score = _clamp(_score_to_100(payload.get("personalized_health_score")), 0.0, 100.0)

    if cut_mode or "fat" in goal_token or "cut" in goal_token:
        if bool(payload.get("cut_friendly")):
            score += 7.0
        elif str(payload.get("cut_warning") or "").strip():
            score -= 6.0
        if bool(payload.get("fat_loss_friendly")):
            score += 5.0

    return _clamp(score, 0.0, 100.0)


def _local_relevance_score(
    payload: Dict[str, Any],
    *,
    fit_for_today: Optional[bool],
    distance_weight: float,
) -> float:
    top = payload.get("top_menu_item") if isinstance(payload.get("top_menu_item"), dict) else {}
    menu_confidence = _clamp(
        _safe_float(
            top.get("menu_item_confidence"),
            _safe_float(payload.get("menu_confidence"), 0.0),
        ),
        0.0,
        1.0,
    )

    source = _normalize_menu_source(
        top.get("menu_item_source")
        or payload.get("menu_source_resolved")
        or payload.get("menu_items_source_resolved")
        or payload.get("menu_source")
        or payload.get("menu_items_source")
    )
    source_rank_weight = _clamp(
        _safe_float(
            top.get("source_rank_weight"),
            SOURCE_RANK_WEIGHTS.get(source, SOURCE_RANK_WEIGHTS["heuristic"]),
        ),
        0.5,
        1.05,
    )
    order_type = str(top.get("order_type") or payload.get("order_type") or "").strip().lower()
    menu_fit_ratio = _clamp(
        _safe_float(
            payload.get("menu_fit_ratio"),
            _safe_float((payload.get("menu_health_signals") or {}).get("menu_fit_ratio"), 0.0),
        ),
        0.0,
        100.0,
    )
    healthy_item_count = int(
        max(
            0,
            _safe_int(
                payload.get("healthy_item_count"),
                _safe_int((payload.get("menu_health_signals") or {}).get("healthy_item_count"), 0),
            ),
        )
    )

    source_bonus = 6.0 if source in {"real_menu", "user_scan"} else 3.0 if source == "llm_inferred" else 1.0
    orderability_bonus = 8.0 if order_type == "exact" else 4.0 if order_type == "likely" else 1.0
    fit_bonus = 8.0 if fit_for_today is True else 3.0 if fit_for_today is None else 0.0
    menu_depth_bonus = min(8.0, healthy_item_count * 1.6)

    local_score = (
        (distance_weight * 50.0)
        + (menu_confidence * 16.0)
        + (source_rank_weight * 18.0)
        + ((menu_fit_ratio / 100.0) * 10.0)
        + menu_depth_bonus
        + source_bonus
        + orderability_bonus
        + fit_bonus
    )
    return _clamp(local_score, 0.0, 100.0)


def _local_ranking_components(
    payload: Dict[str, Any],
    *,
    distance_meters: int,
    fit_for_today: Optional[bool],
    goal: str,
    cut_mode: bool,
) -> Dict[str, Any]:
    dm = int(max(0, _safe_int(distance_meters, 0)))
    distance_band = _distance_band(dm)
    distance_tier = _distance_tier(distance_meters)
    distance_weight = _distance_weight(dm)
    is_current_place = _is_current_place(dm)
    restaurant_health = _restaurant_health_score(payload, goal)
    top_item = _top_item_score(payload)
    fit_score = _fit_for_today_score(payload, fit_for_today)
    top = payload.get("top_menu_item") if isinstance(payload.get("top_menu_item"), dict) else {}
    source = _normalize_menu_source(
        top.get("menu_item_source")
        or payload.get("menu_source_resolved")
        or payload.get("menu_items_source_resolved")
        or payload.get("menu_source")
        or payload.get("menu_items_source")
    )
    source_rank_weight = _clamp(
        _safe_float(
            top.get("source_rank_weight"),
            SOURCE_RANK_WEIGHTS.get(source, SOURCE_RANK_WEIGHTS["heuristic"]),
        ),
        0.5,
        1.05,
    )
    goal_relevance = _goal_relevance_score(
        payload,
        goal=goal,
        cut_mode=bool(cut_mode or payload.get("cut_mode_active")),
        restaurant_health_score=restaurant_health,
    )
    local_relevance = _local_relevance_score(
        payload,
        fit_for_today=fit_for_today,
        distance_weight=distance_weight,
    )

    quality_score = (
        (restaurant_health * 0.40)
        + (top_item * 0.31)
        + (fit_score * 0.19)
        + (goal_relevance * 0.10)
    )
    current_place_bonus = 18.0 if is_current_place else 0.0
    local_priority = (
        (distance_weight * 62.0)
        + (source_rank_weight * 14.0)
        + (_clamp(_safe_float(payload.get("menu_confidence"), 0.0), 0.0, 1.0) * 10.0)
        + (4.0 if fit_for_today is True else 0.0)
        + current_place_bonus
    )
    local_priority = _clamp(local_priority, 0.0, 100.0)
    base_rank_score = (
        (quality_score * 0.60)
        + (local_relevance * 0.14)
        + (local_priority * 0.26)
    )
    base_rank_score = _clamp(base_rank_score, 0.0, 100.0)

    if source == "heuristic" and distance_band in {"2km_to_3km", "over_3km"}:
        base_rank_score = _clamp(base_rank_score - 14.0, 0.0, 100.0)
    elif source == "llm_inferred" and distance_band in {"2km_to_3km", "over_3km"}:
        base_rank_score = _clamp(base_rank_score - 8.0, 0.0, 100.0)
    elif source in {"real_menu", "user_scan"} and distance_band in {"0_to_500m", "500m_to_1km"}:
        base_rank_score = _clamp(base_rank_score + 4.0, 0.0, 100.0)
    if is_current_place:
        base_rank_score = _clamp(base_rank_score + 6.0, 0.0, 100.0)

    modifier_context = {
        "score_channel": "healthy_nearby_local_ranking",
        "goal": str(goal or payload.get("personalization_goal") or "").strip(),
        "cut_mode": bool(cut_mode or payload.get("cut_mode_active")),
        # Phase 1 conservative rollout by default; can be overridden via env/config.
        "modifier_rollout_phase": str(payload.get("modifier_rollout_phase") or ""),
    }
    modifier_result = apply_score_modifiers(
        base_score=base_rank_score,
        payload=payload,
        context=modifier_context,
    )
    final_rank_score = _clamp(_safe_float(modifier_result.get("final_score"), base_rank_score), 0.0, 100.0)
    modifier_score = _safe_float(modifier_result.get("modifier_score"), 0.0)
    modifier_score_raw = _safe_float(modifier_result.get("modifier_score_raw"), 0.0)
    score_adjustment_factor = _safe_float(modifier_result.get("score_adjustment_factor"), 1.0)

    return {
        "distance_band": distance_band,
        "distance_tier": distance_tier,
        "distance_tier_index": _distance_tier_index(distance_tier),
        "distance_weight": round(_clamp(distance_weight, 0.0, 1.0), 3),
        "local_distance_weight": round(_clamp(distance_weight, 0.0, 1.0), 3),
        "restaurant_health_score": round(_clamp(restaurant_health, 0.0, 100.0), 1),
        "top_item_score": round(_clamp(top_item, 0.0, 100.0), 1),
        "fit_for_today_score": round(_clamp(fit_score, 0.0, 100.0), 1),
        "goal_relevance_score": round(_clamp(goal_relevance, 0.0, 100.0), 1),
        "local_relevance_score": round(_clamp(local_relevance, 0.0, 100.0), 1),
        "source_rank_weight": round(_clamp(source_rank_weight, 0.0, 1.1), 2),
        "local_priority_score": round(_clamp(local_priority, 0.0, 100.0), 1),
        "base_score": round(_clamp(base_rank_score, 0.0, 100.0), 2),
        "modifier_score_raw": round(modifier_score_raw, 2),
        "modifier_score": round(modifier_score, 2),
        "final_score": round(_clamp(final_rank_score, 0.0, 100.0), 2),
        "score_adjustment_factor": round(_clamp(score_adjustment_factor, 0.85, 1.15), 4),
        "modifier_rollout_phase": str(modifier_result.get("modifier_rollout_phase") or "phase_1"),
        "modifier_version": str(modifier_result.get("modifier_version") or "v1"),
        "modifier_breakdown": (
            modifier_result.get("modifier_breakdown")
            if isinstance(modifier_result.get("modifier_breakdown"), dict)
            else {}
        ),
        "final_rank_score": round(_clamp(final_rank_score, 0.0, 100.0), 1),
        "local_ranking_score": round(_clamp(final_rank_score, 0.0, 100.0), 1),
        "is_current_place": bool(is_current_place),
        "current_place_priority": bool(is_current_place),
        "current_place_distance_threshold_m": int(CURRENT_PLACE_DISTANCE_MAX_M),
        "local_ranking_version": LOCAL_RANKING_VERSION,
    }


def _restaurant_rank_reason(payload: Dict[str, Any], ranking: Dict[str, Any]) -> str:
    source = _normalize_menu_source(
        (payload.get("top_menu_item") or {}).get("menu_item_source")
        or payload.get("menu_source_resolved")
        or payload.get("menu_items_source_resolved")
        or payload.get("menu_source")
        or payload.get("menu_items_source")
    )
    distance_tier = str(ranking.get("distance_tier") or "")
    distance_band = str(ranking.get("distance_band") or "")
    fit_score = _safe_float(ranking.get("fit_for_today_score"), 0.0)
    menu_fit_ratio = _safe_float(
        payload.get("menu_fit_ratio"),
        _safe_float((payload.get("menu_health_signals") or {}).get("menu_fit_ratio"), 0.0),
    )
    if bool(ranking.get("is_current_place")):
        return "You're here now. Best order here plus healthier nearby alternatives."

    if source in {"real_menu", "user_scan"} and distance_tier == "tier_1" and fit_score >= 70:
        return "Nearby real-menu pick with strong macro fit."
    if source in {"real_menu", "user_scan"} and menu_fit_ratio >= 40:
        return "Real menu shows strong healthy item density."
    if distance_band in {"0_to_500m", "500m_to_1km"} and fit_score >= 65:
        return "Close-by option with practical macro fit."
    if source == "llm_inferred" and fit_score >= 70:
        return "Likely strong option nearby; menu parsing confidence is moderate."
    if source == "heuristic":
        return "Estimated from limited menu data; check menu before ordering."
    return "Balanced nearby option for your current goal."


def _build_badges(payload: Dict[str, Any], fit_for_today: Optional[bool]) -> List[str]:
    out: List[str] = []

    for raw in payload.get("badges") if isinstance(payload.get("badges"), list) else []:
        label = str(raw or "").strip()
        if label:
            out.append(label)

    if not out:
        for raw in payload.get("recommended_badges") if isinstance(payload.get("recommended_badges"), list) else []:
            label = str(raw or "").strip()
            if label:
                out.append(label)

    if fit_for_today is True and "Fits Today's Macros" not in out:
        out.append("Fits Today's Macros")

    if bool(payload.get("cut_friendly") or payload.get("fat_loss_friendly")):
        if "Cut Friendly" not in out and "Fat Loss Friendly" not in out:
            out.append("Cut Friendly")

    deduped: List[str] = []
    seen = set()
    for label in out:
        if label in seen:
            continue
        seen.add(label)
        deduped.append(label)

    return deduped[:4]


def _normalize_menu_source(source: Any) -> str:
    token = str(source or "").strip().lower()
    if token == "user_scan":
        return "user_scan"
    if token in {
        "real_menu",
        "menu_intelligence_store",
        "structured_menu",
        "scraped_menu",
        "user_scan",
        "website_menu",
        "website_text",
        "review_text",
        "ocr_menu",
    }:
        return "real_menu"
    if token in {"llm_inferred", "llm"}:
        return "llm_inferred"
    return "heuristic"


def _display_label_for_menu_item(source: str, confidence: float) -> str:
    conf = _clamp(_safe_float(confidence, 0.5), 0.0, 1.0)
    if source == "real_menu":
        return "Best Menu Item" if conf >= 0.72 else "Likely Better Choice"
    if source == "llm_inferred":
        if conf >= 0.75:
            return "Likely Better Choice"
        if conf >= 0.58:
            return "Suggested Lighter Option"
        if conf >= 0.45:
            return "Estimated Best Fit"
        return "Needs Menu Check"
    if conf >= 0.7:
        return "Estimated Best Fit"
    if conf >= 0.52:
        return "Suggested Lighter Option"
    return "Needs Menu Check"


def _build_top_menu_item(payload: Dict[str, Any], fallback_reason: str) -> Dict[str, Any]:
    top = payload.get("top_menu_item") if isinstance(payload.get("top_menu_item"), dict) else None

    if not top:
        menu_items = payload.get("top_menu_items") if isinstance(payload.get("top_menu_items"), list) else []
        for row in menu_items:
            if isinstance(row, dict):
                top = row
                break

    item_name = str(
        (top or {}).get("item_name")
        or payload.get("best_order")
        or "Lighter menu option"
    ).strip()

    estimated_calories = _safe_int(
        (top or {}).get("estimated_calories"),
        _safe_int(payload.get("estimated_calories"), 0),
    )
    estimated_protein_g = _safe_int(
        (top or {}).get("estimated_protein_g"),
        _safe_int(payload.get("estimated_protein_g"), 0),
    )

    reason = str(
        (top or {}).get("short_reason")
        or payload.get("short_reason")
        or payload.get("why_this_works")
        or fallback_reason
    ).strip()

    source = _normalize_menu_source(
        (top or {}).get("menu_item_source")
        or payload.get("menu_source_resolved")
        or payload.get("menu_items_source_resolved")
        or payload.get("menu_items_source")
        or payload.get("menu_item_source")
    )
    source_rank_weight = _clamp(
        _safe_float(
            (top or {}).get("source_rank_weight"),
            SOURCE_RANK_WEIGHTS.get(source, SOURCE_RANK_WEIGHTS["heuristic"]),
        ),
        0.5,
        1.05,
    )
    confidence = _clamp(
        _safe_float((top or {}).get("menu_item_confidence"), _safe_float((top or {}).get("confidence"), 0.46)),
        0.2,
        0.95,
    )
    context_text = " ".join(
        [
            str(payload.get("place_name") or payload.get("name") or ""),
            str(payload.get("address") or payload.get("vicinity") or ""),
            " ".join(str(t or "") for t in (payload.get("types") if isinstance(payload.get("types"), list) else [])),
            str(payload.get("cuisine_hint") or ""),
        ]
    ).strip()
    safety = sanitize_recommended_item(
        item_name=item_name,
        context_text=context_text,
        menu_item_source=source,
        menu_item_confidence=confidence,
        strong_menu_evidence=has_strong_menu_evidence(
            menu_item_source=source,
            menu_item_confidence=confidence,
            source_url=(top or {}).get("source_url"),
            extraction_method=(top or {}).get("extraction_method"),
            parse_method=(top or {}).get("parse_method"),
            raw_text_snippet=(top or {}).get("raw_text_snippet"),
        ),
        display_label=(top or {}).get("display_label"),
        order_type=(top or {}).get("order_type"),
    )
    item_name = str(safety.get("item_name") or item_name)
    source = str(safety.get("menu_item_source") or source).strip().lower() or "heuristic"
    confidence = _clamp(_safe_float(safety.get("menu_item_confidence"), confidence), 0.2, 0.95)
    source_rank_weight = _clamp(
        _safe_float(
            (top or {}).get("source_rank_weight"),
            SOURCE_RANK_WEIGHTS.get(source, SOURCE_RANK_WEIGHTS["heuristic"]),
        ),
        0.5,
        1.05,
    )
    display_label = str((top or {}).get("display_label") or "").strip() or _display_label_for_menu_item(source, confidence)
    if str(safety.get("display_label") or "").strip():
        display_label = str(safety.get("display_label"))
    swap_suggestion = str(
        (top or {}).get("swap_suggestion")
        or payload.get("swap_suggestion")
        or payload.get("better_swap")
        or "Skip heavy sides and add a lighter side."
    )
    skip_items = (
        (top or {}).get("skip_items")
        if isinstance((top or {}).get("skip_items"), list)
        else payload.get("skip_items")
        if isinstance(payload.get("skip_items"), list)
        else []
    )
    add_items = (
        (top or {}).get("add_items")
        if isinstance((top or {}).get("add_items"), list)
        else payload.get("add_items")
        if isinstance(payload.get("add_items"), list)
        else []
    )
    swap_suggestions = build_swap_suggestions(
        swap_suggestion=swap_suggestion,
        skip_items=skip_items,
        add_items=add_items,
        better_swap=payload.get("better_swap"),
        place_context=context_text,
        menu_item_source=source,
        menu_item_confidence=confidence,
        max_items=3,
    )

    return {
        "item_name": item_name,
        "estimated_calories": max(0, estimated_calories),
        "estimated_protein_g": max(0, estimated_protein_g),
        "short_reason": reason,
        "display_label": display_label,
        "menu_item_source": source,
        "menu_item_confidence": round(confidence, 2),
        "source_rank_weight": round(source_rank_weight, 2),
        "order_type": str(safety.get("order_type") or (top or {}).get("order_type") or ("exact" if source == "real_menu" and confidence >= 0.72 else "likely" if confidence >= 0.56 else "estimated")),
        "menu_item_safety_reason": str(safety.get("safety_reason") or ""),
        "swap_suggestion": swap_suggestion,
        "swap_suggestions": swap_suggestions,
        "skip_items": skip_items,
        "add_items": add_items,
        "order_confidence": round(confidence, 2),
        "copy_method": str((top or {}).get("copy_method") or "deterministic"),
        "copy_confidence": round(
            _clamp(_safe_float((top or {}).get("copy_confidence"), confidence), 0.2, 0.95),
            2,
        ),
        "copy_version": str((top or {}).get("copy_version") or "v1"),
    }


def _build_today_fit(payload: Dict[str, Any], fit_for_today: Optional[bool], fallback_reason: str) -> Dict[str, Any]:
    decision = _decision_token(payload, fit_for_today)

    default_reason = {
        "YES": "Fits today's calories and gives strong protein.",
        "MAYBE": "Can work today with smart swaps.",
        "NO": "Harder to fit your current calories today.",
    }

    decision_reason = str(payload.get("decision_reason") or "").strip() or default_reason.get(decision, fallback_reason)

    return {
        "decision": decision,
        "decision_reason": decision_reason,
        "fits_remaining_calories": payload.get("fits_remaining_calories"),
        "fits_remaining_protein": payload.get("fits_remaining_protein"),
        "decision_confidence": _safe_float(payload.get("decision_confidence"), 0.0),
    }


def _build_reality_check(payload: Dict[str, Any], top_menu_item: Dict[str, Any]) -> Dict[str, Any]:
    base = payload.get("reality_check") if isinstance(payload.get("reality_check"), dict) else {}

    typical_raw = base.get("typical_order") if isinstance(base.get("typical_order"), dict) else {}
    smarter_raw = base.get("smarter_order") if isinstance(base.get("smarter_order"), dict) else {}

    typical_name = str(typical_raw.get("name") or "Typical combo meal").strip()
    typical_calories = _safe_int(typical_raw.get("estimated_calories"), 0)
    if typical_calories <= 0:
        typical_calories = max(0, _safe_int(payload.get("estimated_calories"), 0) + 320)

    smarter_name = str(
        smarter_raw.get("name")
        or top_menu_item.get("item_name")
        or payload.get("best_order")
        or "Smarter order"
    ).strip()
    smarter_calories = _safe_int(
        smarter_raw.get("estimated_calories"),
        _safe_int(top_menu_item.get("estimated_calories"), _safe_int(payload.get("estimated_calories"), 0)),
    )
    smarter_protein = _safe_int(
        smarter_raw.get("estimated_protein_g"),
        _safe_int(top_menu_item.get("estimated_protein_g"), _safe_int(payload.get("estimated_protein_g"), 0)),
    )

    calories_saved = _safe_int(base.get("calories_saved"), typical_calories - smarter_calories)
    calories_saved = max(0, calories_saved)

    short_reason = str(base.get("short_reason") or "").strip()
    if not short_reason:
        short_reason = (
            f"You save {calories_saved} kcal with a smarter order."
            if calories_saved > 0
            else "Better calorie control with stronger protein."
        )

    merged = dict(base)
    merged.update(
        {
            "typical_order": {
                "name": typical_name,
                "estimated_calories": max(0, typical_calories),
            },
            "smarter_order": {
                "name": smarter_name,
                "estimated_calories": max(0, smarter_calories),
                "estimated_protein_g": max(0, smarter_protein),
            },
            "calories_saved": calories_saved,
            "short_reason": short_reason,
        }
    )
    return merged


# Canonical section order for sectioned_mode
SECTION_ORDER: List[str] = [
    "Best fit for your goal",
    "Decent nearby options",
    "Needs menu check",
]


def _section_rank(section: Any) -> int:
    s = str(section or "").strip().lower()
    if "best fit" in s or "best fit for your goal" in s:
        return 0
    if "decent" in s:
        return 1
    if "needs menu check" in s:
        return 2
    return 1


def _display_score_100(payload: Dict[str, Any]) -> float:
    v = _safe_float(payload.get("display_rank_score_100") or payload.get("health_score_100"), 0.0) or 0.0
    if 0 < v <= 10:
        v *= 10.0
    return v


def _sort_score_100(payload: Dict[str, Any]) -> float:
    """Use specificity-aware sort score when available (favors chain/menu over generic)."""
    sort_score = payload.get("display_sort_score_100")
    if sort_score is not None and str(sort_score).strip() != "":
        return float(sort_score)
    return _display_score_100(payload)


def _flat_sort_key(payload: Dict[str, Any]) -> tuple:
    """Visible order = display_sort_score_100 desc (or display_rank_score_100), distance asc."""
    score = _sort_score_100(payload)
    distance = _safe_float(payload.get("distance_meters"), 10_000_000.0)
    return (-score, distance)


def _sectioned_sort_key(payload: Dict[str, Any]) -> tuple:
    """Section rank, then sort score desc, then distance asc."""
    section_r = _section_rank(payload.get("section"))
    score = _sort_score_100(payload)
    distance = _safe_float(payload.get("distance_meters"), 10_000_000.0)
    return (section_r, -score, distance)


def build_sections(places: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group places by section; each section has name and items (sorted by display_rank_score_100 desc, distance)."""
    by_section: Dict[str, List[Dict[str, Any]]] = {}
    for p in places:
        sec = str(p.get("section") or "Decent nearby options").strip()
        if sec not in by_section:
            by_section[sec] = []
        by_section[sec].append(p)
    for sec_list in by_section.values():
        sec_list.sort(key=_flat_sort_key)
    sections = []
    for name in SECTION_ORDER:
        if name in by_section and by_section[name]:
            sections.append({"name": name, "items": by_section[name]})
    for name, items in by_section.items():
        if name not in SECTION_ORDER:
            sections.append({"name": name, "items": items})
    return sections


def enrich_places_for_healthy_map(
    places: List[Dict[str, Any]],
    *,
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    goal: str = "",
    cut_mode: bool = False,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    sort_mode: str = "sectioned",
) -> List[Dict[str, Any]]:
    """Enrich places with map/display fields. sort_mode: 'flat_score' | 'sectioned'. Flat = order by display_rank_score_100 desc, distance (no current_place bump)."""
    src = [dict(row) for row in (places or []) if isinstance(row, dict)]
    if not src:
        return []

    out: List[Dict[str, Any]] = []
    for row in src:
        # Meal-first: visible score = display_rank_score_100 (must match list sort)
        display_rank = row.get("display_rank_score_100")
        if display_rank is not None and str(display_rank).strip() != "":
            score_100 = int(round(_safe_float(display_rank, 0.0)))
        else:
            score_value = row.get("personalized_health_score") if row.get("personalized_health_score") is not None else row.get("health_score")
            score_100 = _score_to_100(score_value)
        band = _score_band(score_100)
        fit = _fit_for_today(row)

        lat = _safe_float(row.get("lat"), float("nan"))
        lng = _safe_float(row.get("lng"), float("nan"))
        distance_m = _haversine_meters(origin_lat, origin_lng, lat, lng)
        if distance_m is None:
            existing = _safe_float(row.get("distance_meters"), -1)
            # Unknown coordinates should not get an accidental "closest place" boost.
            distance_m = int(existing) if existing >= 0 else 3500

        place_name = str(row.get("place_name") or row.get("name") or "Nearby place").strip() or "Nearby place"
        place_id = str(row.get("place_id") or row.get("id") or "").strip()

        why = str(
            row.get("why_this_works")
            or row.get("short_reason")
            or row.get("personalized_reason")
            or row.get("decision_reason")
            or "Better choice nearby for your goal."
        ).strip()

        cta_label = str(row.get("cta_label") or "").strip()
        if not cta_label:
            cta_label = "Navigate" if fit is not False else "View alternatives"

        top_menu_item = _build_top_menu_item(row, why)
        today_fit = _build_today_fit(row, fit, why)
        reality_check = _build_reality_check(row, top_menu_item)
        coach_message = build_place_coach_message(
            place=row,
            top_menu_item=top_menu_item,
            today_fit=today_fit,
            reality_check=reality_check,
            context={
                "goal": str(goal or row.get("personalization_goal") or "").strip(),
                "cut_mode": bool(cut_mode or row.get("cut_mode_active")),
                "remaining_calories": remaining_calories,
                "remaining_protein_g": remaining_protein_g,
            },
        )

        ranking = _local_ranking_components(
            row,
            distance_meters=int(max(0, distance_m)),
            fit_for_today=fit,
            goal=str(goal or row.get("personalization_goal") or "").strip(),
            cut_mode=bool(cut_mode or row.get("cut_mode_active")),
        )
        restaurant_rank_reason = _restaurant_rank_reason(row, ranking)

        enriched = dict(row)
        enriched.update(
            {
                "place_id": place_id,
                "place_name": place_name,
                "distance_meters": int(max(0, distance_m)),
                "health_score_100": int(score_100),
                "display_rank_score_100": int(score_100),
                "section": str(row.get("section") or "Decent nearby options").strip(),
                "score_band": band,
                "map_pin_color": _map_pin_color(band),
                "map_pin_hex": _map_pin_hex(band),
                "map_rank": int(_safe_int(row.get("map_rank"), 0)),
                "map_priority": int(_safe_int(row.get("map_priority"), 1)),
                "map_label": f"{place_name} • {int(score_100)}",
                "fit_for_today": fit,
                "decision_today": today_fit["decision"],
                "badges": _build_badges(row, fit),
                "why_this_works": why,
                "cta_label": cta_label,
                **ranking,
                "menu_item_source": top_menu_item.get("menu_item_source"),
                "menu_item_confidence": top_menu_item.get("menu_item_confidence"),
                "source_rank_weight": top_menu_item.get("source_rank_weight", ranking.get("source_rank_weight")),
                "swap_suggestion": top_menu_item.get("swap_suggestion"),
                "swap_suggestions": (
                    top_menu_item.get("swap_suggestions")
                    if isinstance(top_menu_item.get("swap_suggestions"), list)
                    else []
                )[:3],
                "current_place_label": "You're here now" if bool(ranking.get("is_current_place")) else "",
                "restaurant_rank_reason": restaurant_rank_reason,
                "rank_reason": restaurant_rank_reason,
                # Compact map intelligence blocks for selected-pin panel rendering.
                "top_menu_item": top_menu_item,
                "today_fit": today_fit,
                "reality_check": reality_check,
                "coach_message": coach_message,
                "intelligence_panel": {
                    "coach_message": coach_message,
                    "top_menu_item": top_menu_item,
                    "today_fit": today_fit,
                    "reality_check": reality_check,
                },
            }
        )
        out.append(enriched)

    if sort_mode == "flat_score":
        out.sort(key=_flat_sort_key)
    else:
        out.sort(key=_sectioned_sort_key)
    for idx, row in enumerate(out, start=1):
        row["map_rank"] = int(idx)
        row["map_priority"] = int(max(1, 100 - idx))

    return out


def _apply_limit_with_current_place(rows: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    if not rows:
        return []
    clipped = list(rows[: max(1, int(max_items))])
    if any(bool(r.get("is_current_place")) for r in clipped):
        return clipped

    current_candidates = [r for r in rows if bool(r.get("is_current_place"))]
    if not current_candidates:
        return clipped

    current_candidates.sort(
        key=lambda r: (
            _safe_float(r.get("distance_meters"), 10_000_000.0),
            -_safe_float(r.get("final_rank_score"), _safe_float(r.get("local_ranking_score"), 0.0)),
        )
    )
    replacement = current_candidates[0]
    if len(clipped) >= 1:
        clipped[-1] = replacement
    else:
        clipped = [replacement]
    return clipped


def build_healthy_food_map_response(
    *,
    places: List[Dict[str, Any]],
    lat: float,
    lng: float,
    radius: int,
    goal: str = "",
    cut_mode: bool = False,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    limit: int = 40,
) -> Dict[str, Any]:
    enriched = enrich_places_for_healthy_map(
        places,
        origin_lat=float(_safe_float(lat, 0.0) or 0.0),
        origin_lng=float(_safe_float(lng, 0.0) or 0.0),
        goal=str(goal or "").strip(),
        cut_mode=bool(cut_mode),
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
    )

    max_items = max(1, min(80, int(_safe_float(limit, 40) or 40)))
    clipped = _apply_limit_with_current_place(enriched, max_items)

    return {
        "title": "Healthy Food Map",
        "subtitle": "Best places near you",
        "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "map_context": {
            "lat": round(float(_safe_float(lat, 0.0) or 0.0), 6),
            "lng": round(float(_safe_float(lng, 0.0) or 0.0), 6),
            "radius": int(max(200, min(5000, int(_safe_float(radius, 2000) or 2000))),),
            "goal": str(goal or "").strip(),
            "cut_mode": bool(cut_mode),
            "current_place_distance_threshold_m": int(CURRENT_PLACE_DISTANCE_MAX_M),
        },
        "places": clipped,
        "healthy_food_map_version": HEALTHY_FOOD_MAP_VERSION,
    }
