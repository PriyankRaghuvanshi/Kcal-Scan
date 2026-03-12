"""
Healthy Nearby fast path: shortlist before deep ranking.
Reduces work by deeply scoring only promising places.
No LLM in hot path. No live menu fetching.
"""
from __future__ import annotations

import math
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from place_trace_debug import infer_specificity_tier

DEFAULT_SHORTLIST_SIZE = 10
MAX_SHORTLIST_SIZE = 20

# Cheap chain check: place name substrings that suggest chain registry match
_CHEAP_CHAIN_TOKENS = (
    "subway", "mcdonald", "maccas", "macca", "hungry jack", "hj ", "nando", "grill'd",
    "grilld", "guzman", "gyg", "oporto", "red rooster", "kfc", "domino", "pizza hut",
    "zambrero", "boost juice", "sushi hub", "burger king", "bk ",
)

# Place types that score higher in pre-rank (restaurant-like)
_RELEVANT_TYPES = (
    "restaurant", "meal_takeaway", "meal_delivery", "cafe", "food",
    "sandwich", "fast_food", "bakery",
)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _place_text(place: Dict[str, Any]) -> str:
    name = str(place.get("name") or "").strip().lower()
    types = place.get("types") or []
    type_str = " ".join(str(t or "").lower() for t in types)
    return f"{name} {type_str}"


def _cheap_chain_match(place: Dict[str, Any]) -> bool:
    """Quick check: does place name contain a known chain token? Does not load registry."""
    text = _place_text(place)
    return any(t in text for t in _CHEAP_CHAIN_TOKENS)


def _pre_rank_score(
    place: Dict[str, Any],
    *,
    origin_lat: float = 0.0,
    origin_lng: float = 0.0,
    cache_has: Optional[Callable[[str], bool]] = None,
) -> float:
    """
    Cheap pre-rank score 0-100. Used only to shortlist.
    Factors: distance, type relevance, chain presence, cache hit, rating.
    """
    score = 50.0
    lat = _safe_float(place.get("lat"), 0.0)
    lng = _safe_float(place.get("lng"), 0.0)
    place_id = str(place.get("place_id") or place.get("id") or "").strip()
    types = place.get("types") or []
    name = str(place.get("name") or "").strip().lower()

    # Distance: closer = better. Approximate meters.
    if math.isfinite(lat) and math.isfinite(lng) and origin_lat and origin_lng:
        km = math.hypot((lat - origin_lat) * 111, (lng - origin_lng) * 111 * max(0.7, math.cos(math.radians(lat))))
        dist_m = km * 1000
        if dist_m <= 500:
            score += 25
        elif dist_m <= 1000:
            score += 18
        elif dist_m <= 2000:
            score += 10
        elif dist_m <= 3000:
            score += 2
        else:
            score -= 10

    # Type relevance
    type_lower = [str(t or "").lower() for t in types]
    if any(t in type_lower for t in _RELEVANT_TYPES):
        score += 12

    # Chain likely match
    if _cheap_chain_match(place):
        score += 15

    # Cache hit
    if cache_has and place_id and cache_has(place_id):
        score += 12

    # Rating count (if available)
    rating_count = _safe_float(place.get("user_ratings_total"), 0)
    if rating_count >= 100:
        score += 5
    elif rating_count >= 20:
        score += 2

    return max(0.0, min(100.0, score))


def shortlist_places(
    places: List[Dict[str, Any]],
    *,
    shortlist_size: int = DEFAULT_SHORTLIST_SIZE,
    origin_lat: float = 0.0,
    origin_lng: float = 0.0,
    cache_has: Optional[Callable[[str], bool]] = None,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Split places into shortlisted (for deep rank) and skipped.
    Returns (shortlisted, skipped, debug_info).
    """
    shortlist_size = max(2, min(MAX_SHORTLIST_SIZE, int(shortlist_size or DEFAULT_SHORTLIST_SIZE)))
    if not places:
        return [], [], {"fetched_count": 0, "shortlisted_count": 0, "skipped_count": 0}

    scored: List[Tuple[float, Dict[str, Any], str]] = []
    for p in places:
        pre_score = _pre_rank_score(p, origin_lat=origin_lat, origin_lng=origin_lng, cache_has=cache_has)
        reason = "shortlisted" if pre_score >= 40 else "low_pre_rank"
        scored.append((pre_score, p, reason))

    scored.sort(key=lambda x: (-x[0], x[1].get("name") or ""))

    shortlisted = []
    skipped = []
    for i, (pre_score, p, _) in enumerate(scored):
        p_copy = dict(p)
        p_copy["_pre_rank_score"] = round(pre_score, 1)
        p_copy["_pre_rank_reason"] = "shortlisted" if i < shortlist_size else "low_pre_rank"
        if i < shortlist_size:
            shortlisted.append(p_copy)
        else:
            skipped.append(p_copy)

    debug = {
        "fetched_count": len(places),
        "shortlisted_count": len(shortlisted),
        "skipped_count": len(skipped),
        "shortlist_size": shortlist_size,
        "skipped_reasons": {
            "low_pre_rank": sum(1 for _, _, r in scored[shortlist_size:] if r == "low_pre_rank"),
        },
    }
    return shortlisted, skipped, debug


def run_fast_path(
    places: List[Dict[str, Any]],
    *,
    deep_rank_fn: Callable[[List[Dict[str, Any]]], List[Dict[str, Any]]],
    origin_lat: float = 0.0,
    origin_lng: float = 0.0,
    shortlist_size: int = DEFAULT_SHORTLIST_SIZE,
    cache_has: Optional[Callable[[str], bool]] = None,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """
    Run fast path: shortlist then deep rank only shortlisted.
    deep_rank_fn(places) -> scored_places. Called only for shortlisted.
    """
    timings = {}
    t0 = time.perf_counter()

    shortlisted, skipped, shortlist_debug = shortlist_places(
        places,
        shortlist_size=shortlist_size,
        origin_lat=origin_lat,
        origin_lng=origin_lng,
        cache_has=cache_has,
    )
    timings["shortlist_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    t1 = time.perf_counter()
    scored = deep_rank_fn(shortlisted) if shortlisted else []
    timings["ranking_ms"] = round((time.perf_counter() - t1) * 1000, 1)
    timings["total_ms"] = round((time.perf_counter() - t0) * 1000, 1)

    return scored, {
        "timings": timings,
        "fetched_count": shortlist_debug["fetched_count"],
        "shortlisted_count": shortlist_debug["shortlisted_count"],
        "deeply_ranked_count": len(scored),
        "skipped_count": shortlist_debug["skipped_count"],
        "shortlist_debug": shortlist_debug,
    }
