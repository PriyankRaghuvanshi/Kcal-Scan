from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from coach_messages import build_place_coach_message


HEALTHY_FOOD_MAP_VERSION = "v1"
LOCAL_RANKING_VERSION = "v1"

DISTANCE_TIER_1_MAX_M = 800
DISTANCE_TIER_2_MAX_M = 1500
DISTANCE_TIER_3_MAX_M = 3000


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
    if dm <= DISTANCE_TIER_1_MAX_M:
        # 0-800m strongly preferred for practical walkability.
        return _clamp(1.0 - ((dm / float(DISTANCE_TIER_1_MAX_M)) * 0.18), 0.82, 1.0)
    if dm <= DISTANCE_TIER_2_MAX_M:
        # 800m-1.5km still practical but clearly less convenient.
        ratio = (dm - DISTANCE_TIER_1_MAX_M) / float(DISTANCE_TIER_2_MAX_M - DISTANCE_TIER_1_MAX_M)
        return _clamp(0.82 - (ratio * 0.23), 0.59, 0.82)
    if dm <= DISTANCE_TIER_3_MAX_M:
        # 1.5km-3km keep available but with meaningful penalty.
        ratio = (dm - DISTANCE_TIER_2_MAX_M) / float(DISTANCE_TIER_3_MAX_M - DISTANCE_TIER_2_MAX_M)
        return _clamp(0.59 - (ratio * 0.31), 0.28, 0.59)
    # Beyond 3km stays eligible for clearly superior options only.
    tail = min(1.0, (dm - DISTANCE_TIER_3_MAX_M) / 2000.0)
    return _clamp(0.28 - (tail * 0.12), 0.16, 0.28)


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
        or payload.get("menu_source")
        or payload.get("menu_items_source")
    )
    order_type = str(top.get("order_type") or payload.get("order_type") or "").strip().lower()

    source_bonus = 4.0 if source == "real_menu" else 2.0 if source == "llm_inferred" else 1.0
    orderability_bonus = 8.0 if order_type == "exact" else 4.0 if order_type == "likely" else 1.0
    fit_bonus = 8.0 if fit_for_today is True else 3.0 if fit_for_today is None else 0.0

    local_score = (
        (distance_weight * 55.0)
        + (menu_confidence * 25.0)
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
    distance_tier = _distance_tier(distance_meters)
    distance_weight = _distance_weight(distance_meters)
    restaurant_health = _restaurant_health_score(payload, goal)
    top_item = _top_item_score(payload)
    fit_score = _fit_for_today_score(payload, fit_for_today)
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
        + (top_item * 0.28)
        + (fit_score * 0.18)
        + (goal_relevance * 0.14)
    )
    local_rank = (
        (quality_score * 0.62)
        + (local_relevance * 0.23)
        + ((distance_weight * 100.0) * 0.15)
    )

    return {
        "distance_tier": distance_tier,
        "distance_tier_index": _distance_tier_index(distance_tier),
        "distance_weight": round(_clamp(distance_weight, 0.0, 1.0), 3),
        "restaurant_health_score": round(_clamp(restaurant_health, 0.0, 100.0), 1),
        "top_item_score": round(_clamp(top_item, 0.0, 100.0), 1),
        "fit_for_today_score": round(_clamp(fit_score, 0.0, 100.0), 1),
        "goal_relevance_score": round(_clamp(goal_relevance, 0.0, 100.0), 1),
        "local_relevance_score": round(_clamp(local_relevance, 0.0, 100.0), 1),
        "local_ranking_score": round(_clamp(local_rank, 0.0, 100.0), 1),
        "local_ranking_version": LOCAL_RANKING_VERSION,
    }


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
        or payload.get("menu_items_source")
        or payload.get("menu_item_source")
    )
    confidence = _clamp(
        _safe_float((top or {}).get("menu_item_confidence"), _safe_float((top or {}).get("confidence"), 0.46)),
        0.2,
        0.95,
    )
    display_label = str((top or {}).get("display_label") or "").strip() or _display_label_for_menu_item(source, confidence)

    return {
        "item_name": item_name,
        "estimated_calories": max(0, estimated_calories),
        "estimated_protein_g": max(0, estimated_protein_g),
        "short_reason": reason,
        "display_label": display_label,
        "menu_item_source": source,
        "menu_item_confidence": round(confidence, 2),
        "order_type": str((top or {}).get("order_type") or ("exact" if source == "real_menu" and confidence >= 0.72 else "likely" if confidence >= 0.56 else "estimated")),
        "swap_suggestion": str((top or {}).get("swap_suggestion") or payload.get("swap_suggestion") or payload.get("better_swap") or "Skip heavy sides and add a lighter side."),
        "skip_items": (
            (top or {}).get("skip_items")
            if isinstance((top or {}).get("skip_items"), list)
            else payload.get("skip_items")
            if isinstance(payload.get("skip_items"), list)
            else []
        ),
        "add_items": (
            (top or {}).get("add_items")
            if isinstance((top or {}).get("add_items"), list)
            else payload.get("add_items")
            if isinstance(payload.get("add_items"), list)
            else []
        ),
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


def _sort_key(payload: Dict[str, Any]) -> tuple:
    local_rank = _safe_float(payload.get("local_ranking_score"), 0.0)
    tier_idx = int(_safe_int(payload.get("distance_tier_index"), 4))
    distance = _safe_float(payload.get("distance_meters"), 10_000_000.0)
    fit_score = _safe_float(payload.get("fit_for_today_score"), 0.0)
    health = _safe_float(payload.get("restaurant_health_score"), _safe_float(payload.get("health_score"), 0.0))
    return (-local_rank, tier_idx, distance, -fit_score, -health)


def enrich_places_for_healthy_map(
    places: List[Dict[str, Any]],
    *,
    origin_lat: Optional[float] = None,
    origin_lng: Optional[float] = None,
    goal: str = "",
    cut_mode: bool = False,
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
) -> List[Dict[str, Any]]:
    src = [dict(row) for row in (places or []) if isinstance(row, dict)]
    if not src:
        return []

    out: List[Dict[str, Any]] = []
    for row in src:
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

        enriched = dict(row)
        enriched.update(
            {
                "place_id": place_id,
                "place_name": place_name,
                "distance_meters": int(max(0, distance_m)),
                "health_score_100": int(score_100),
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

    out.sort(key=_sort_key)
    for idx, row in enumerate(out, start=1):
        row["map_rank"] = int(idx)
        row["map_priority"] = int(max(1, 100 - idx))

    return out


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
    clipped = enriched[:max_items]

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
        },
        "places": clipped,
        "healthy_food_map_version": HEALTHY_FOOD_MAP_VERSION,
    }
