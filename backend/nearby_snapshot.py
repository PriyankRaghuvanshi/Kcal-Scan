from __future__ import annotations

"""
Shared nearby snapshot service for Healthy Nearby / Decision mode.

This module does NOT change any existing endpoint shapes yet.
It provides a single canonical ranking pipeline that other
endpoints (e.g. /places/healthy, /places/lunch-decision) can
gradually adopt.

Design goals:
- Reuse existing scoring / enrichment logic.
- Avoid duplicated work per place.
- Conservative current-venue detection.
- Keep public surface simple and stable.
"""

from typing import Any, Dict, List, Optional

from better_choice_nearby import haversine_meters, _build_place_profile


def _safe_float(v: Any, default: float = 0.0) -> float:
  try:
    return float(v)
  except Exception:
    return float(default)


def _norm_text(text: Any) -> str:
  return " ".join(str(text or "").strip().lower().split())


def _distance_from_origin(profile: Dict[str, Any], origin_lat: float, origin_lng: float) -> Optional[int]:
  try:
    lat = _safe_float(profile.get("lat"), 0.0)
    lng = _safe_float(profile.get("lng"), 0.0)
    if not lat and not lng:
      return None
    return haversine_meters(origin_lat, origin_lng, lat, lng)
  except Exception:
    return None


def _build_ranked_profiles(
  nearby_places: List[Dict[str, Any]],
  *,
  origin_lat: float,
  origin_lng: float,
) -> List[Dict[str, Any]]:
  """
  Build a normalized + ranked profile list from raw nearby places.

  This uses the same underlying place-profile builder that the
  "better choice nearby" service uses, to avoid duplicating
  scoring and enrichment logic.
  """
  profiles: List[Dict[str, Any]] = []
  for place in (nearby_places or []):
    if not isinstance(place, dict):
      continue
    try:
      profile = _build_place_profile(place)
    except Exception:
      # Fallback: skip pathological rows instead of breaking the pipeline.
      continue
    distance_m = _distance_from_origin(profile, origin_lat, origin_lng)
    if distance_m is not None:
      profile["distance_meters"] = int(distance_m)
    profiles.append(profile)

  # Sort by the same core signal stack used elsewhere in the codebase:
  # - health score (10-pt)
  # - protein (g)
  # - calories (lower is better)
  # - distance (closer is better)
  def _sort_key(p: Dict[str, Any]):
    health_10 = _safe_float(p.get("health_score_10pt"), 5.0)
    protein = _safe_float(p.get("estimated_protein_g"), 0.0)
    calories = _safe_float(p.get("estimated_calories"), 999.0)
    distance = _safe_float(p.get("distance_meters"), 10_000.0)
    # Higher health/protein, lower calories/distance.
    return (
      float(health_10),
      float(protein),
      -float(calories),
      -float(distance),
    )

  profiles.sort(key=_sort_key, reverse=True)
  return profiles


def _detect_current_venue(
  ranked_profiles: List[Dict[str, Any]],
  *,
  origin_lat: float,
  origin_lng: float,
  selected_place_id: str = "",
  selected_place_name: str = "",
) -> Optional[Dict[str, Any]]:
  """
  Conservative current-venue detection.

  Signals:
  - Explicit selected_place_id (e.g. from map or smart alert).
  - Name similarity (normalized text).
  - Distance threshold (<= ~40 m strong, <= ~80 m moderate).
  """
  if not ranked_profiles:
    return None

  sel_id = str(selected_place_id or "").strip()
  sel_name_norm = _norm_text(selected_place_name)

  best_profile: Optional[Dict[str, Any]] = None
  best_score = -1.0

  for prof in ranked_profiles:
    pid = str(prof.get("place_id") or "").strip()
    name_norm = _norm_text(prof.get("name"))
    distance_m = _distance_from_origin(prof, origin_lat, origin_lng) or 99999

    score = 0.0

    # Strong hint: exact selected id.
    if sel_id and pid and sel_id == pid:
      score += 4.0

    # Name similarity if explicit name provided.
    if sel_name_norm and name_norm:
      if sel_name_norm == name_norm:
        score += 3.0
      elif sel_name_norm in name_norm or name_norm in sel_name_norm:
        score += 2.0

    # Distance bands.
    if distance_m <= 20:
      score += 4.0
    elif distance_m <= 40:
      score += 3.0
    elif distance_m <= 80:
      score += 2.0
    elif distance_m <= 150:
      score += 1.0

    if score > best_score:
      best_score = score
      best_profile = prof

  # Require both a minimum confidence score and that we are not clearly far away.
  if not best_profile:
    return None
  distance_m = _distance_from_origin(best_profile, origin_lat, origin_lng) or 99999
  if best_score < 4.0:
    return None
  if distance_m > 80:
    return None

  return {
    "place_id": str(best_profile.get("place_id") or "").strip(),
    "name": str(best_profile.get("name") or "").strip(),
    "distance_m": int(distance_m),
    "match_confidence": round(min(0.99, max(0.0, best_score / 10.0)), 2),
  }


def _derive_best_here_and_nearby(
  ranked_profiles: List[Dict[str, Any]],
  current_venue: Optional[Dict[str, Any]],
) -> Dict[str, Optional[Dict[str, Any]]]:
  if not ranked_profiles:
    return {"best_here": None, "best_nearby": None}

  best_nearby = ranked_profiles[0]

  best_here = None
  if current_venue:
    vid = str(current_venue.get("place_id") or "").strip()
    for prof in ranked_profiles:
      if str(prof.get("place_id") or "").strip() == vid:
        best_here = prof
        break

  def _to_summary(p: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not p:
      return None
    return {
      "place_id": str(p.get("place_id") or "").strip(),
      "name": str(p.get("name") or "").strip(),
      "best_item_name": str(p.get("best_order") or p.get("top_menu_item", {}).get("item_name") or "").strip(),
      "best_item_calories": int(_safe_float(p.get("estimated_calories"), 0.0) or 0),
      "best_item_protein": int(_safe_float(p.get("estimated_protein_g"), 0.0) or 0),
      "display_rank_score_100": int(_safe_float(p.get("health_score"), 0.0) or 0),
      "rank_reason_short": str(p.get("short_reason") or "").strip(),
      "distance_meters": int(_safe_float(p.get("distance_meters"), 0.0) or 0),
    }

  return {
    "best_here": _to_summary(best_here) if best_here else None,
    "best_nearby": _to_summary(best_nearby),
  }


def build_nearby_snapshot(
  *,
  nearby_places: List[Dict[str, Any]],
  origin_lat: float,
  origin_lng: float,
  radius_m: int,
  goal: str,
  cut_mode: bool,
  remaining_calories: Optional[float],
  remaining_protein_g: Optional[float],
  current_hour: Optional[int],
  user_id: Optional[str],
  selected_place_id: str = "",
  selected_place_name: str = "",
) -> Dict[str, Any]:
  """
  Build a canonical nearby snapshot:
  - ranked_places: normalized + ranked place profiles
  - current_venue: conservative best guess of where the user is
  - best_here: best option at the current_venue (if any)
  - best_nearby: best option overall

  For this first step:
  - We do NOT yet change any endpoint responses.
  - We intentionally do not over-index on goal / cut_mode; those
    signals are already baked into the place scoring logic that
    _build_place_profile uses.
  """
  ranked_profiles = _build_ranked_profiles(
    nearby_places or [],
    origin_lat=float(_safe_float(origin_lat, 0.0) or 0.0),
    origin_lng=float(_safe_float(origin_lng, 0.0) or 0.0),
  )

  current_venue = _detect_current_venue(
    ranked_profiles,
    origin_lat=float(_safe_float(origin_lat, 0.0) or 0.0),
    origin_lng=float(_safe_float(origin_lng, 0.0) or 0.0),
    selected_place_id=selected_place_id,
    selected_place_name=selected_place_name,
  )
  best_summary = _derive_best_here_and_nearby(ranked_profiles, current_venue)

  snapshot: Dict[str, Any] = {
    "version": "v1",
    "user_location": {
      "lat": float(_safe_float(origin_lat, 0.0) or 0.0),
      "lng": float(_safe_float(origin_lng, 0.0) or 0.0),
      "radius_m": int(_safe_float(radius_m, 0.0) or 0),
    },
    "context": {
      "goal": str(goal or "").strip(),
      "cut_mode": bool(cut_mode),
      "remaining_calories": float(_safe_float(remaining_calories, 0.0)) if remaining_calories is not None else None,
      "remaining_protein_g": float(_safe_float(remaining_protein_g, 0.0)) if remaining_protein_g is not None else None,
      "current_hour": int(_safe_float(current_hour, -1.0)) if current_hour is not None else None,
      "user_id": str(user_id or "").strip() or None,
    },
    "current_venue": current_venue,
    "best_here": best_summary["best_here"],
    "best_nearby": best_summary["best_nearby"],
    "ranked_places": ranked_profiles,
  }
  return snapshot

