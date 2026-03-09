from __future__ import annotations

import math
from typing import Any, Dict, List

from healthy_order_recommender import suggest_best_order_for_place
from healthy_place_scoring import score_healthy_place
from menu_item_scoring import recommend_menu_items_for_place
from recommendation_safety import has_strong_menu_evidence, sanitize_recommended_item


BETTER_CHOICE_VERSION = "v1"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _norm_text(text: Any) -> str:
    return " ".join(str(text or "").strip().lower().split())


def haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> int:
    # Lightweight distance estimate for local nearby ranking.
    r = 6371000.0
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dlat = p2 - p1
    dlng = math.radians(float(lng2) - float(lng1))
    a = math.sin(dlat / 2.0) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return int(max(0.0, r * c))


def estimate_walk_time_minutes(distance_meters: int, pace_m_per_min: float = 80.0) -> int:
    # ~4.8 km/h walking pace default.
    mins = float(distance_meters) / max(20.0, float(pace_m_per_min))
    return int(max(1, round(mins)))


def estimate_drive_time_minutes(distance_meters: int, avg_speed_kmh: float = 22.0) -> int:
    # Conservative city-driving context.
    speed_m_per_min = max(100.0, float(avg_speed_kmh) * 1000.0 / 60.0)
    mins = float(distance_meters) / speed_m_per_min
    return int(max(1, round(mins)))


def _build_place_profile(place: Dict[str, Any]) -> Dict[str, Any]:
    payload = place if isinstance(place, dict) else {}

    scoring = score_healthy_place(payload)
    health_score_10pt = float(_safe_float(scoring.get("health_score"), 5.0) or 5.0)

    order = suggest_best_order_for_place(payload, health_score=health_score_10pt)
    menu = recommend_menu_items_for_place(payload, health_score=health_score_10pt)
    top_menu_item = menu.get("top_menu_item") if isinstance(menu.get("top_menu_item"), dict) else None

    menu_source = str((top_menu_item or {}).get("menu_item_source") or menu.get("menu_source") or "heuristic").strip().lower()
    menu_conf = float(_safe_float((top_menu_item or {}).get("menu_item_confidence"), _safe_float((top_menu_item or {}).get("confidence"), 0.0)) or 0.0)
    context_text = " ".join(
        [
            str(payload.get("name") or ""),
            str(payload.get("vicinity") or payload.get("address") or ""),
            " ".join(str(t or "") for t in (payload.get("types") if isinstance(payload.get("types"), list) else [])),
        ]
    ).strip()
    safety = sanitize_recommended_item(
        item_name=(top_menu_item or {}).get("item_name") or order.get("best_order") or "Lighter menu option",
        context_text=context_text,
        menu_item_source=menu_source,
        menu_item_confidence=menu_conf if menu_conf > 0 else _safe_float(order.get("order_confidence"), 0.45),
        strong_menu_evidence=has_strong_menu_evidence(
            menu_item_source=menu_source,
            menu_item_confidence=menu_conf,
            source_url=(top_menu_item or {}).get("source_url"),
            extraction_method=(top_menu_item or {}).get("extraction_method"),
            parse_method=(top_menu_item or {}).get("parse_method"),
            raw_text_snippet=(top_menu_item or {}).get("raw_text_snippet"),
        ),
    )
    best_order = str(safety.get("item_name") or (top_menu_item or {}).get("item_name") or order.get("best_order") or "Lighter menu option")
    est_calories = int(_safe_float((top_menu_item or {}).get("estimated_calories"), _safe_float(order.get("estimated_calories"), 520)) or 520)
    est_protein = int(_safe_float((top_menu_item or {}).get("estimated_protein_g"), _safe_float(order.get("estimated_protein_g"), 32)) or 32)
    short_reason = str((top_menu_item or {}).get("short_reason") or order.get("short_reason") or "Better protein-calorie balance.")
    estimated_satiety = str((top_menu_item or {}).get("estimated_satiety") or order.get("estimated_satiety") or "medium")
    order_confidence = float(_safe_float(order.get("order_confidence"), 0.46) or 0.46)

    return {
        "name": str(payload.get("name") or "").strip(),
        "place_id": str(payload.get("place_id") or "").strip(),
        "lat": float(_safe_float(payload.get("lat"), 0.0) or 0.0),
        "lng": float(_safe_float(payload.get("lng"), 0.0) or 0.0),
        "address": str(payload.get("address") or payload.get("vicinity") or "").strip(),
        "rating": float(_safe_float(payload.get("rating"), 0.0) or 0.0),
        "types": payload.get("types") if isinstance(payload.get("types"), list) else [],
        "health_score_10pt": round(_clamp(health_score_10pt, 1.0, 10.0), 1),
        "health_score": int(round(_clamp(health_score_10pt * 10.0, 10.0, 100.0))),
        "score_breakdown": scoring.get("score_breakdown") if isinstance(scoring.get("score_breakdown"), dict) else {},
        "best_order": best_order,
        "estimated_calories": est_calories,
        "estimated_protein_g": est_protein,
        "short_reason": short_reason,
        "estimated_satiety": estimated_satiety,
        "order_confidence": round(_clamp(order_confidence, 0.0, 1.0), 2),
        "menu_item_scoring_available": bool(menu.get("menu_item_scoring_available", False)),
        "top_menu_item": top_menu_item,
    }


def _selected_match(profile: Dict[str, Any], selected_place_name: str, selected_place_id: str) -> bool:
    if selected_place_id and str(profile.get("place_id") or "") == selected_place_id:
        return True

    if selected_place_name:
        selected_norm = _norm_text(selected_place_name)
        prof_norm = _norm_text(profile.get("name"))
        if selected_norm and (selected_norm in prof_norm or prof_norm in selected_norm):
            return True
    return False


def _derive_selected_profile(
    place_profiles: List[Dict[str, Any]],
    selected_place_name: str,
    selected_place_id: str,
    origin_lat: float,
    origin_lng: float,
) -> Dict[str, Any]:
    for profile in place_profiles:
        if _selected_match(profile, selected_place_name, selected_place_id):
            return profile

    # Fallback profile when selected place is not in nearby result set.
    synthetic = {
        "name": str(selected_place_name or "Selected place").strip() or "Selected place",
        "place_id": str(selected_place_id or "").strip(),
        "lat": float(_safe_float(origin_lat, 0.0) or 0.0),
        "lng": float(_safe_float(origin_lng, 0.0) or 0.0),
        "types": ["restaurant"],
        "address": "",
    }
    profile = _build_place_profile(synthetic)
    # Conservative bias: if selected place is unknown, avoid over-promoting tiny differences.
    profile["health_score_10pt"] = min(float(profile["health_score_10pt"]), 5.4)
    profile["health_score"] = int(round(profile["health_score_10pt"] * 10.0))
    return profile


def _why_better(selected: Dict[str, Any], alt: Dict[str, Any]) -> str:
    selected_breakdown = selected.get("score_breakdown") if isinstance(selected.get("score_breakdown"), dict) else {}
    alt_breakdown = alt.get("score_breakdown") if isinstance(alt.get("score_breakdown"), dict) else {}

    def score_of(src: Dict[str, Any], key: str) -> float:
        entry = src.get(key) if isinstance(src.get(key), dict) else {}
        return float(_safe_float(entry.get("score"), 5.0) or 5.0)

    protein_gain = score_of(alt_breakdown, "protein_density") - score_of(selected_breakdown, "protein_density")
    calorie_gain = score_of(alt_breakdown, "calorie_control") - score_of(selected_breakdown, "calorie_control")

    if protein_gain >= 0.8 and calorie_gain >= 0.8:
        return "Higher protein and better calorie control than your selected place."
    if protein_gain >= 0.8:
        return "More protein-forward menu options than your selected place."
    if calorie_gain >= 0.8:
        return "Better calorie-control choices than your selected place."
    return "Overall healthier food profile for fat-loss goals."


def build_better_choice_nearby_response(
    nearby_places: List[Dict[str, Any]],
    selected_place_name: str,
    selected_place_id: str = "",
    origin_lat: float = 0.0,
    origin_lng: float = 0.0,
    min_score_delta: float = 1.2,
    limit: int = 5,
) -> Dict[str, Any]:
    profiles = [_build_place_profile(place) for place in (nearby_places or []) if isinstance(place, dict)]

    selected = _derive_selected_profile(
        profiles,
        selected_place_name=selected_place_name,
        selected_place_id=selected_place_id,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
    )

    selected_lat = float(_safe_float(selected.get("lat"), origin_lat) or origin_lat)
    selected_lng = float(_safe_float(selected.get("lng"), origin_lng) or origin_lng)
    selected_score = float(_safe_float(selected.get("health_score_10pt"), 5.0) or 5.0)

    alternatives: List[Dict[str, Any]] = []
    for alt in profiles:
        if _selected_match(alt, selected.get("name", ""), selected.get("place_id", "")):
            continue

        alt_score = float(_safe_float(alt.get("health_score_10pt"), 5.0) or 5.0)
        score_delta = alt_score - selected_score
        if score_delta < float(min_score_delta):
            continue

        distance_m = haversine_meters(selected_lat, selected_lng, alt.get("lat", 0.0), alt.get("lng", 0.0))
        walk_mins = estimate_walk_time_minutes(distance_m)
        drive_mins = estimate_drive_time_minutes(distance_m)

        alternatives.append(
            {
                "name": alt.get("name"),
                "health_score": int(_safe_float(alt.get("health_score"), 50) or 50),
                "health_score_10pt": float(_safe_float(alt.get("health_score_10pt"), 5.0) or 5.0),
                "distance_meters": int(distance_m),
                "walk_time_minutes": int(walk_mins),
                "drive_time_minutes": int(drive_mins),
                "why_better": _why_better(selected, alt),
                "best_order": str(alt.get("best_order") or "Lighter menu option"),
                "estimated_calories": int(_safe_float(alt.get("estimated_calories"), 520) or 520),
                "estimated_protein_g": int(_safe_float(alt.get("estimated_protein_g"), 32) or 32),
                "short_reason": str(alt.get("short_reason") or "Better protein-calorie profile."),
                "estimated_satiety": str((alt.get("top_menu_item") or {}).get("estimated_satiety") or alt.get("estimated_satiety") or "medium"),
                "confidence": round(float(_safe_float((alt.get("top_menu_item") or {}).get("confidence"), _safe_float(alt.get("order_confidence"), 0.46)) or 0.46), 2),
                "score_delta": round(float(score_delta), 2),
                "top_menu_item": alt.get("top_menu_item") if isinstance(alt.get("top_menu_item"), dict) else None,
            }
        )

    alternatives.sort(
        key=lambda row: (
            -float(_safe_float(row.get("score_delta"), 0.0) or 0.0),
            int(_safe_float(row.get("distance_meters"), 0) or 0),
        )
    )

    max_items = max(0, min(10, int(_safe_float(limit, 5) or 5)))
    selected_clean = {
        "name": selected.get("name"),
        "health_score": int(_safe_float(selected.get("health_score"), 50) or 50),
        "health_score_10pt": float(_safe_float(selected.get("health_score_10pt"), 5.0) or 5.0),
        "best_order": selected.get("best_order"),
        "estimated_calories": int(_safe_float(selected.get("estimated_calories"), 520) or 520),
        "estimated_protein_g": int(_safe_float(selected.get("estimated_protein_g"), 32) or 32),
        "lat": float(_safe_float(selected.get("lat"), origin_lat) or origin_lat),
        "lng": float(_safe_float(selected.get("lng"), origin_lng) or origin_lng),
    }

    return {
        "selected_place": selected_clean,
        "better_choices_nearby": alternatives[:max_items],
        "better_choice_scoring_available": bool(alternatives),
        "selected_place_found_in_nearby": any(_selected_match(p, selected_place_name, selected_place_id) for p in profiles),
        "better_choice_version": BETTER_CHOICE_VERSION,
    }
