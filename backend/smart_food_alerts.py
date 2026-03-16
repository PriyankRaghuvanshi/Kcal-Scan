"""
Smart Food Alerts — context-aware nearby notifications.

Only fires when: user need exists, timing/context is right, nearby quality is high,
fatigue/spam checks allow it. Deterministic, no LLM.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Strong personal memory labels (worked_before_repeat)
STRONG_PERSONAL_LABELS = (
    "Worked well before",
    "Usually keeps you fuller",
    "You often repeat this",
)

# Minimum scores/thresholds
MIN_DISPLAY_SCORE_PROTEIN_RESCUE = 65
MIN_DISPLAY_SCORE_GENERAL = 62
MIN_DISPLAY_SCORE_WORKED_BEFORE = 58
MIN_PROTEIN_PROTEIN_RESCUE = 20
MIN_PROTEIN_POST_WORKOUT = 20
MIN_CONFIDENCE = "Estimated"  # "Needs menu check" → suppress
ALERT_SCORE_THRESHOLD = 55
MAX_ALERTS_6H = 1
MAX_ALERTS_24H = 2
MAX_ALERTS_WEEKLY = 5
IGNORED_STREAK_REDUCE_AT = 3
MAX_SAME_VENUE_ALERTS_24H = 1


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return default


def _confidence_ok(place: Dict[str, Any]) -> bool:
    conf = str(place.get("confidence_label") or "").strip()
    return conf in ("Verified", "Estimated") and conf != "Needs menu check"


def _is_dinner_window(local_hour: int) -> bool:
    return 16 <= local_hour <= 20


def _is_late_night(local_hour: int, context_mode: str, late_night_flag: bool) -> bool:
    return late_night_flag or local_hour >= 21 or context_mode == "late_night_damage_control"


def _is_post_workout(post_workout: bool, context_mode: str) -> bool:
    return post_workout or context_mode == "post_workout_recovery"


def _has_strong_personal_label(place: Dict[str, Any]) -> bool:
    label = str(place.get("personal_memory_label") or "").strip()
    return label in STRONG_PERSONAL_LABELS and bool(place.get("worked_before"))


def _check_suppression(
    user_context: Dict[str, Any],
    alert_type: str,
    place_id: str,
) -> List[str]:
    """Return list of suppression reasons, empty if eligible."""
    reasons: List[str] = []
    recent_6h = _safe_int(user_context.get("recent_alerts_count_6h"), 0)
    recent_24h = _safe_int(user_context.get("recent_alerts_count_24h"), 0)
    weekly = _safe_int(user_context.get("weekly_alert_count"), 0)
    ignored = _safe_int(user_context.get("ignored_streak"), 0)
    recently_opened = bool(user_context.get("recently_opened_app"))
    recently_viewed = bool(user_context.get("recently_viewed_nearby"))
    recent_venue_alerts = user_context.get("recent_venue_alert_ids") or {}

    if recent_6h >= MAX_ALERTS_6H:
        reasons.append("max_alerts_6h")
    if recent_24h >= MAX_ALERTS_24H:
        reasons.append("max_alerts_24h")
    if weekly >= MAX_ALERTS_WEEKLY:
        reasons.append("max_alerts_weekly")
    if ignored >= IGNORED_STREAK_REDUCE_AT:
        reasons.append("ignored_streak")
    if place_id and recent_venue_alerts.get(place_id, 0) >= MAX_SAME_VENUE_ALERTS_24H:
        reasons.append("same_venue_recently")
    if recently_opened and recently_viewed:
        reasons.append("user_already_saw_nearby")
    return reasons


def _score_need(alert_type: str, user_context: Dict[str, Any]) -> float:
    remaining_protein = _safe_float(user_context.get("remaining_protein_g"), 0)
    remaining_cal = _safe_float(user_context.get("remaining_calories"), 0)
    post_workout = _is_post_workout(
        bool(user_context.get("post_workout")),
        str(user_context.get("context_mode") or ""),
    )
    late_night = _is_late_night(
        _safe_int(user_context.get("local_hour"), 12),
        str(user_context.get("context_mode") or ""),
        bool(user_context.get("late_night")),
    )
    poor_sleep = bool(user_context.get("poor_sleep_flag"))
    high_craving = bool(user_context.get("high_craving_risk_flag"))

    score = 0.0
    if alert_type == "protein_rescue":
        if remaining_protein >= 25:
            score = min(30, 10 + remaining_protein * 0.5)
    elif alert_type == "post_workout_recovery":
        if post_workout and remaining_protein >= 20:
            score = 25
    elif alert_type == "late_night_damage_control":
        if late_night:
            score = 22
    elif alert_type == "worked_before_repeat":
        score = 20  # personal relevance drives this
    elif alert_type == "habit_rescue":
        if poor_sleep or high_craving:
            score = 18
    return score


def _score_timing(alert_type: str, user_context: Dict[str, Any]) -> float:
    local_hour = _safe_int(user_context.get("local_hour"), 12)
    post_workout = _is_post_workout(
        bool(user_context.get("post_workout")),
        str(user_context.get("context_mode") or ""),
    )
    late_night = _is_late_night(
        local_hour,
        str(user_context.get("context_mode") or ""),
        bool(user_context.get("late_night")),
    )

    score = 0.0
    if alert_type == "protein_rescue":
        if _is_dinner_window(local_hour) or (16 <= local_hour <= 20):
            score = 15
        elif 11 <= local_hour <= 15:
            score = 10
    elif alert_type == "post_workout_recovery":
        if post_workout:
            score = 15
    elif alert_type == "late_night_damage_control":
        if late_night:
            score = 15
    elif alert_type in ("worked_before_repeat", "habit_rescue"):
        score = 8
    return score


def _score_nearby_quality(place: Dict[str, Any], alert_type: str) -> float:
    display = _safe_int(place.get("display_rank_score_100"), 0)
    protein = _safe_float(place.get("best_item_protein") or place.get("estimated_protein_g"), 0)
    distance_m = _safe_float(place.get("distance_meters"), 2000)
    rec_label = str(place.get("recommendation_label") or "")
    min_score = MIN_DISPLAY_SCORE_PROTEIN_RESCUE if alert_type == "protein_rescue" else MIN_DISPLAY_SCORE_GENERAL
    if alert_type == "worked_before_repeat":
        min_score = MIN_DISPLAY_SCORE_WORKED_BEFORE

    score = 0.0
    if display >= 80:
        score += 25
    elif display >= 70:
        score += 18
    elif display >= min_score:
        score += 10
    else:
        return 0

    dist_bonus = max(0, 10 - distance_m / 500)
    score += min(10, dist_bonus)
    if "Best pick" in rec_label or "Strong option" in rec_label:
        score += 5
    if alert_type in ("protein_rescue", "post_workout_recovery") and protein >= 30:
        score += 5
    return score


def _score_personal_relevance(place: Dict[str, Any], alert_type: str) -> float:
    if alert_type != "worked_before_repeat":
        return 0.0
    if not _has_strong_personal_label(place):
        return 0.0
    score = 20
    if place.get("swap_accept_rate") and float(place.get("swap_accept_rate", 0)) >= 0.6:
        score += 5
    if place.get("times_chosen", 0) >= 4:
        score += 5
    return score


def _score_fatigue(user_context: Dict[str, Any]) -> float:
    recent_6h = _safe_int(user_context.get("recent_alerts_count_6h"), 0)
    recent_24h = _safe_int(user_context.get("recent_alerts_count_24h"), 0)
    weekly = _safe_int(user_context.get("weekly_alert_count"), 0)
    ignored = _safe_int(user_context.get("ignored_streak"), 0)
    return min(30, recent_6h * 15 + recent_24h * 5 + weekly * 2 + ignored * 8)


def _normalize_notification_tone(tone: Any) -> str:
    t = str(tone or "supportive").strip().lower()
    if t in ("strict", "funny", "indian_coach", "indian"):
        return "indian_coach" if t in ("indian_coach", "indian") else t
    return "supportive"


def _apply_notification_tone(title: str, body: str, tone: str, name: str, protein: int, distance_min: int) -> Tuple[str, str]:
    """Rewrite title/body for push notification tone (strict, funny, indian_coach)."""
    if tone == "supportive":
        return title, body
    if tone == "strict":
        # Shorter, direct
        if "protein" in title.lower() or "protein" in body.lower():
            return "Protein fix nearby", f"{name} — {protein}g protein." if protein else f"{name}. Lock it in."
        if "recovery" in title.lower():
            return "Recovery option nearby", f"{name} — {protein}g protein."
        if "late" in title.lower():
            return "Late option that still fits", f"{name}."
        if "done well" in title.lower():
            return "You repeated this before", f"{name} nearby."
        return "Good fit nearby", body
    if tone == "funny":
        # One hook phrase
        if "protein" in title.lower() or "protein" in body.lower():
            return "Pro move: protein nearby", f"{name} — {protein}g in ~{distance_min} min."
        if "recovery" in title.lower():
            return "Recovery cheat code", f"{name} — {protein}g protein."
        if "late" in title.lower():
            return "Plot twist: still fits", f"{name}."
        if "done well" in title.lower():
            return "Boss move: you liked this before", f"{name} is nearby."
        return "Solid pick nearby", body
    if tone == "indian_coach":
        # Natural Hinglish
        if "protein" in title.lower() or "protein" in body.lower():
            return "Protein fix passand hai", f"{name} — {protein}g protein, thoda door (~{distance_min} min)."
        if "recovery" in title.lower():
            return "Recovery ke liye sahi", f"{name} — {protein}g protein."
        if "late" in title.lower():
            return "Late night bhi theek", f"{name} abhi bhi fit hai."
        if "done well" in title.lower():
            return "Pehle bhi try kiya tha", f"{name} ab nearby hai."
        if "habit" in title.lower() or "regret" in title.lower():
            return "Lower-regret pick", f"{name} — goal ke hisaab se."
        return "Best nearby fit", f"{name} — {protein}g protein." if protein else f"{name} — fits your goal."
    return title, body


def _build_alert_templates(
    alert_type: str,
    place: Dict[str, Any],
    user_context: Dict[str, Any],
) -> Tuple[str, str]:
    name = str(place.get("name") or place.get("place_name") or "nearby spot").strip()
    protein = _safe_int(place.get("best_item_protein") or place.get("estimated_protein_g"), 0)
    remaining = _safe_float(user_context.get("remaining_protein_g"), 0)
    protein_gap = max(0, int(remaining) - 20) if remaining > 0 else 0
    distance_m = _safe_float(place.get("distance_meters"), 500)
    distance_min = max(1, int(distance_m / 80))
    local_hour = _safe_int(user_context.get("local_hour"), 12)
    tone = _normalize_notification_tone(user_context.get("tone_preference"))

    if alert_type == "protein_rescue":
        # Time-of-day aware copy; avoid blunt deficit messaging, especially in evening.
        if local_hour >= 19:
            if protein >= 30:
                title = "Best realistic dinner move tonight"
                body = f"{name} — about {protein}g protein in ~{distance_min} min."
            else:
                title = "Lighter protein-focused option tonight"
                body = f"{name} — a smaller protein boost that still helps this evening."
        elif 11 <= local_hour <= 15:
            if protein_gap >= 25 and protein >= 30:
                title = "A protein-focused meal now would help"
                body = f"{name} — about {protein}g protein, a strong next move for today."
            else:
                title = "You still have a good protein window"
                body = f"{name} — a protein-focused choice nearby ({protein}g)."
        else:
            if protein_gap >= 25 and protein >= 30:
                title = "A 30–40g protein meal would help"
                body = f"{name} — about {protein}g protein in ~{distance_min} min."
            else:
                title = "Good protein fit nearby"
                body = f"{name} — about {protein}g protein."
    elif alert_type == "post_workout_recovery":
        title = "Post-workout recovery nearby"
        body = f"Best nearby recovery: {name} — {protein}g protein in ~{distance_min} min."
    elif alert_type == "late_night_damage_control":
        title = "Hungry late?"
        body = f"This nearby option still fits today: {name}."
    elif alert_type == "worked_before_repeat":
        title = "You've done well with this before"
        body = f"{name} is nearby now."
    elif alert_type == "habit_rescue":
        title = "Lower-regret pick nearby"
        body = f"{name} — fits your goal."
    else:
        title = "Best nearby fit right now"
        body = f"{name} — {protein}g protein." if protein else f"{name} — fits your goal."
    return _apply_notification_tone(title, body, tone, name, protein, distance_min)


def _why_triggered(alert_type: str, place: Dict[str, Any], user_context: Dict[str, Any]) -> str:
    parts = [f"need:{alert_type}"]
    display = place.get("display_rank_score_100")
    protein = place.get("best_item_protein") or place.get("estimated_protein_g")
    if display is not None:
        parts.append(f"score:{display}")
    if protein is not None:
        parts.append(f"protein:{protein}g")
    dist = place.get("distance_meters")
    if dist is not None:
        parts.append(f"dist:{int(dist)}m")
    return "|".join(parts)


def _build_one_candidate(
    alert_type: str,
    place: Dict[str, Any],
    user_context: Dict[str, Any],
    suppression_reasons: List[str],
) -> Dict[str, Any]:
    need = _score_need(alert_type, user_context)
    timing = _score_timing(alert_type, user_context)
    quality = _score_nearby_quality(place, alert_type)
    personal = _score_personal_relevance(place, alert_type)
    fatigue = _score_fatigue(user_context)
    alert_score = max(0, min(100, int(round(need + timing + quality + personal - fatigue))))
    # Prefer different venues day to day: down-rank places we already suggested in last 24h
    place_id_val = str(place.get("place_id") or place.get("id") or "")
    recent_place_ids = user_context.get("recent_sent_place_ids_24h")
    if isinstance(recent_place_ids, (set, list)) and place_id_val in (recent_place_ids or ()):
        alert_score = max(0, alert_score - 30)
    title, body = _build_alert_templates(alert_type, place, user_context)
    eligible = (
        alert_score >= ALERT_SCORE_THRESHOLD
        and not suppression_reasons
        and _confidence_ok(place)
    )
    return {
        "alert_type": alert_type,
        "alert_score": alert_score,
        "title": title,
        "body": body,
        "place_id": str(place.get("place_id") or place.get("id") or ""),
        "place_name": str(place.get("name") or place.get("place_name") or ""),
        "place_lat": _safe_float(place.get("lat")) if place.get("lat") is not None else None,
        "place_lng": _safe_float(place.get("lng")) if place.get("lng") is not None else None,
        "best_item_name": str(place.get("best_item_name") or place.get("best_order") or ""),
        "display_rank_score_100": place.get("display_rank_score_100"),
        "distance_m": _safe_int(place.get("distance_meters")),
        "estimated_calories": place.get("best_item_calories") or place.get("estimated_calories"),
        "estimated_protein_g": place.get("best_item_protein") or place.get("estimated_protein_g"),
        "confidence_label": str(place.get("confidence_label") or ""),
        "recommendation_label": str(place.get("recommendation_label") or ""),
        "personal_memory_label": str(place.get("personal_memory_label") or ""),
        "chosen_candidate_specificity_tier": str(place.get("chosen_candidate_specificity_tier") or ""),
        "menu_item_source": str(place.get("menu_item_source") or place.get("best_item_source") or ""),
        "matched_local_profile": bool(place.get("matched_local_profile") or place.get("_matched_local_profile")),
        "local_profile_source": str(place.get("local_profile_source") or place.get("_local_profile_source") or ""),
        "used_venue_intelligence_cache": bool(place.get("used_venue_intelligence_cache") or place.get("_used_venue_intelligence_cache")),
        "best_item_is_generic_fallback": bool(place.get("best_item_is_generic_fallback")),
        "context_mode": str(user_context.get("context_mode") or "default"),
        "why_triggered": _why_triggered(alert_type, place, user_context),
        "suppression_reasons": suppression_reasons,
        "eligible_to_send": eligible,
    }


def build_smart_food_alert_candidates(
    user_context: Dict[str, Any],
    ranked_places: List[Dict[str, Any]],
    *,
    eligible_only: bool = False,
) -> List[Dict[str, Any]]:
    """
    Build smart food alert candidates from ranked places.

    Returns list of alert candidate dicts. Each has: alert_type, alert_score, title, body,
    place_id, place_name, best_item_name, display_rank_score_100, distance_m,
    estimated_calories, estimated_protein_g, confidence_label, recommendation_label,
    personal_memory_label, context_mode, why_triggered, suppression_reasons, eligible_to_send.
    """
    if not ranked_places:
        return []
    places = [p for p in ranked_places if isinstance(p, dict)][:20]
    remaining_protein = _safe_float(user_context.get("remaining_protein_g"), 0)
    remaining_cal = _safe_float(user_context.get("remaining_calories"), 0)
    local_hour = _safe_int(user_context.get("local_hour"), 12)
    context_mode = str(user_context.get("context_mode") or "default")
    post_workout = _is_post_workout(bool(user_context.get("post_workout")), context_mode)
    late_night = _is_late_night(
        local_hour, context_mode, bool(user_context.get("late_night")),
    )
    poor_sleep = bool(user_context.get("poor_sleep_flag"))
    high_craving = bool(user_context.get("high_craving_risk_flag"))

    candidates: List[Dict[str, Any]] = []
    seen_types: set = set()

    for place in places:
        if not _confidence_ok(place):
            continue
        display = _safe_int(place.get("display_rank_score_100"), 0)
        protein = _safe_float(place.get("best_item_protein") or place.get("estimated_protein_g"), 0)
        place_id = str(place.get("place_id") or place.get("id") or "")

        # A. protein_rescue
        if (
            "protein_rescue" not in seen_types
            and remaining_protein >= 25
            and 16 <= local_hour <= 20
            and protein >= MIN_PROTEIN_PROTEIN_RESCUE
            and display >= MIN_DISPLAY_SCORE_PROTEIN_RESCUE
        ):
            supp = _check_suppression(user_context, "protein_rescue", place_id)
            c = _build_one_candidate("protein_rescue", place, user_context, supp)
            candidates.append(c)
            seen_types.add("protein_rescue")

        # B. post_workout_recovery
        if (
            "post_workout_recovery" not in seen_types
            and post_workout
            and remaining_protein >= 20
            and protein >= MIN_PROTEIN_POST_WORKOUT
            and display >= MIN_DISPLAY_SCORE_GENERAL
        ):
            supp = _check_suppression(user_context, "post_workout_recovery", place_id)
            c = _build_one_candidate("post_workout_recovery", place, user_context, supp)
            candidates.append(c)
            seen_types.add("post_workout_recovery")

        # C. late_night_damage_control
        if (
            "late_night_damage_control" not in seen_types
            and late_night
            and display >= MIN_DISPLAY_SCORE_GENERAL
            and protein >= 15
        ):
            supp = _check_suppression(user_context, "late_night_damage_control", place_id)
            c = _build_one_candidate("late_night_damage_control", place, user_context, supp)
            candidates.append(c)
            seen_types.add("late_night_damage_control")

        # D. worked_before_repeat
        if (
            "worked_before_repeat" not in seen_types
            and _has_strong_personal_label(place)
            and display >= MIN_DISPLAY_SCORE_WORKED_BEFORE
        ):
            supp = _check_suppression(user_context, "worked_before_repeat", place_id)
            c = _build_one_candidate("worked_before_repeat", place, user_context, supp)
            candidates.append(c)
            seen_types.add("worked_before_repeat")

        # E. habit_rescue
        if (
            "habit_rescue" not in seen_types
            and (poor_sleep or high_craving)
            and display >= MIN_DISPLAY_SCORE_GENERAL
        ):
            supp = _check_suppression(user_context, "habit_rescue", place_id)
            c = _build_one_candidate("habit_rescue", place, user_context, supp)
            candidates.append(c)
            seen_types.add("habit_rescue")

    if eligible_only:
        candidates = [c for c in candidates if c.get("eligible_to_send")]
    candidates.sort(key=lambda c: (-(c.get("alert_score") or 0), c.get("distance_m") or 9999))
    return candidates


def build_alert_audit_one_liner(candidate: Dict[str, Any]) -> str:
    """One-line string for audit/debug: protein_rescue | Score 91 | Subway | 30g protein | 4 min away | eligible"""
    atype = candidate.get("alert_type", "?")
    score = candidate.get("alert_score", 0)
    name = candidate.get("place_name", "?")
    protein = candidate.get("estimated_protein_g")
    dist_m = candidate.get("distance_m") or 0
    dist_min = max(1, int(dist_m / 80))
    status = "eligible" if candidate.get("eligible_to_send") else "suppressed"
    supp = candidate.get("suppression_reasons") or []
    if supp:
        status = f"suppressed:{','.join(supp[:2])}"
    parts = [atype, f"Score {score}", name]
    if protein is not None:
        parts.append(f"{protein}g protein")
    parts.append(f"{dist_min} min away")
    parts.append(status)
    return " | ".join(parts)
