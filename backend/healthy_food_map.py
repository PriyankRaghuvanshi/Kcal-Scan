from __future__ import annotations

import datetime as dt
import math
from typing import Any, Dict, List, Optional

from coach_messages import build_place_coach_message


HEALTHY_FOOD_MAP_VERSION = "v1"


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
    if token in {"real_menu", "menu_intelligence_store", "structured_menu", "scraped_menu", "user_scan"}:
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
    rank = _safe_float(payload.get("map_rank"), 10_000.0)
    score_primary = _safe_float(payload.get("personalized_health_score"), _safe_float(payload.get("health_score"), 0.0))
    fit = 1 if _fit_for_today(payload) is True else 0
    distance = _safe_float(payload.get("distance_meters"), 10_000_000.0)
    return (rank, -fit, -score_primary, distance)


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

    src.sort(key=_sort_key)

    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(src, start=1):
        score_value = row.get("personalized_health_score") if row.get("personalized_health_score") is not None else row.get("health_score")
        score_100 = _score_to_100(score_value)
        band = _score_band(score_100)
        fit = _fit_for_today(row)

        lat = _safe_float(row.get("lat"), float("nan"))
        lng = _safe_float(row.get("lng"), float("nan"))
        distance_m = _haversine_meters(origin_lat, origin_lng, lat, lng)
        if distance_m is None:
            existing = _safe_float(row.get("distance_meters"), -1)
            distance_m = int(existing) if existing >= 0 else 0

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
                "map_rank": int(idx),
                "map_priority": int(max(1, 100 - idx)),
                "map_label": f"{place_name} • {int(score_100)}",
                "fit_for_today": fit,
                "decision_today": today_fit["decision"],
                "badges": _build_badges(row, fit),
                "why_this_works": why,
                "cta_label": cta_label,
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
