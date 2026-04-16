from __future__ import annotations

import datetime as dt
from typing import Any, Dict, List, Optional

from weekly_coach import build_weekly_coach_payload


GOAL_COACH_VERSION = "v1"
# Let's Go: free trial for 3 weeks, then require Advanced plan to continue.
FREE_KICKOFF_DAYS = 21


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)


def _safe_str(v: Any) -> str:
    return str(v or "").strip()


def _today() -> dt.date:
    return dt.date.today()


def _parse_day_iso(day_iso: str) -> Optional[dt.date]:
    try:
        return dt.date.fromisoformat((day_iso or "")[:10])
    except Exception:
        return None


def _parse_date_ymd(raw: str) -> Optional[dt.date]:
    s = _safe_str(raw)
    if not s:
        return None
    try:
        return dt.date.fromisoformat(s[:10])
    except Exception:
        return None


def build_starter_plan(plan_input: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministic starter-plan generation for Let’s Go Goal Coach.
    Does not depend on LLM; pure rules on simple fields.
    """
    goal_type = _safe_str(plan_input.get("goal_type") or "fat_loss").lower()
    pace_mode = _safe_str(plan_input.get("pace_mode") or "balanced").lower()
    timeframe_weeks = _safe_int(plan_input.get("timeframe_weeks") or 0, 0)
    training_days = _safe_int(plan_input.get("training_days_per_week") or 0, 0)
    diet_pref = _safe_str(plan_input.get("diet_preference")).lower()

    current_weight = _safe_float(plan_input.get("current_weight"), 0.0)
    target_weight = _safe_float(plan_input.get("target_weight"), 0.0)

    # Simple calorie heuristics based on goal + pace.
    base_cal = 2300.0
    if goal_type == "fat_loss":
        base_cal = 2000.0
    elif goal_type == "muscle_gain":
        base_cal = 2600.0
    elif goal_type == "recomp":
        base_cal = 2200.0

    if pace_mode == "easy":
        cal_adj = 0.9
    elif pace_mode == "serious":
        cal_adj = 0.8 if goal_type == "fat_loss" else 1.05
    else:
        cal_adj = 1.0

    target_calories = round(base_cal * cal_adj)

    # Protein target: default to 1.8–2.0 g/kg-ish where weight is available.
    if current_weight > 0:
        # Assume kg if plausible; otherwise convert from lbs.
        kg = current_weight if current_weight < 200 else current_weight / 2.2
        multiplier = 1.8 if goal_type == "fat_loss" else 2.0
        target_protein = int(round(kg * multiplier))
    else:
        target_protein = 130 if goal_type in {"fat_loss", "recomp"} else 150

    # Simple macro split.
    protein_cals = target_protein * 4
    remaining_cals = max(0, target_calories - protein_cals)
    carb_cals = int(remaining_cals * (0.45 if goal_type == "muscle_gain" else 0.35))
    fat_cals = max(0, remaining_cals - carb_cals)

    target_carbs = int(round(carb_cals / 4)) if carb_cals > 0 else 0
    target_fat = int(round(fat_cals / 9)) if fat_cals > 0 else 0

    weeks = max(4, timeframe_weeks or 8)
    if goal_type == "fat_loss":
        pace_label = "steady"
        if pace_mode == "easy":
            pace_label = "gentle"
        elif pace_mode == "serious":
            pace_label = "aggressive but still reasonable"
        weekly_focus = "Keep protein high, tighten late-night calories, and anchor 2–3 meals."
        risk_note = "Fast cuts with low protein are more likely to backfire; consistency beats extremes."
    elif goal_type == "muscle_gain":
        pace_label = "lean gain"
        weekly_focus = "Hit protein on training days and keep surplus modest on rest days."
        risk_note = "Huge surpluses mostly add fat; small surpluses plus strong protein work better."
    elif goal_type == "recomp":
        pace_label = "slow recomposition"
        weekly_focus = "Alternate slightly lower-calorie rest days with strong protein training days."
        risk_note = "Recomp is slower but more sustainable; expect smaller week-to-week shifts."
    else:
        pace_label = "maintenance"
        weekly_focus = "Keep calories and protein steady while watching weekend drift."
        risk_note = "Maintenance still needs some structure or drift tends to creep in."

    actions: List[str] = []
    actions.append("Scan or log at least 2 key meals per day.")
    if training_days >= 3:
        actions.append("Plan one higher-protein meal around each training session.")
    else:
        actions.append("Anchor breakfast and dinner with 30–40g protein where possible.")
    if goal_type == "fat_loss":
        actions.append("Keep late-night snacks under 200 kcal on weeknights.")
    else:
        actions.append("Prioritize whole-food protein and carbs over liquid calories.")

    expected_pace = {
        "goal_type": goal_type,
        "pace_mode": pace_mode,
        "timeframe_weeks": weeks,
        "label": pace_label,
    }

    return {
        "version": GOAL_COACH_VERSION,
        "goal_type": goal_type,
        "pace_mode": pace_mode,
        "timeframe_weeks": weeks,
        "target_calories": target_calories,
        "target_protein_g": target_protein,
        "target_carbs_g": target_carbs,
        "target_fat_g": target_fat,
        "expected_pace": expected_pace,
        "weekly_focus": weekly_focus,
        "risk_note": risk_note,
        "first_actions": actions[:3],
        "diet_preference": diet_pref or None,
        "training_days_per_week": training_days or None,
        "current_weight": current_weight or None,
        "target_weight": target_weight or None,
    }


def compute_kickoff_status(plan: Dict[str, Any], today: Optional[dt.date] = None) -> Dict[str, Any]:
    day = today or _today()
    kickoff_raw = plan.get("kickoff_started_at") or plan.get("created_at") or ""
    kickoff_date = _parse_date_ymd(str(kickoff_raw))
    if not kickoff_date:
        kickoff_date = day
    delta_days = max(0, (day - kickoff_date).days)
    used = min(delta_days + 1, FREE_KICKOFF_DAYS)
    in_kickoff = used <= FREE_KICKOFF_DAYS
    return {
        "free_kickoff_days": FREE_KICKOFF_DAYS,
        "kickoff_days_used": used,
        "in_kickoff": in_kickoff,
        "requires_subscription": not in_kickoff,
    }


def build_daily_coach_state(
    plan: Dict[str, Any],
    daily_metrics: Optional[Dict[str, Any]] = None,
    memory_signals: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    daily = daily_metrics if isinstance(daily_metrics, dict) else {}
    mem = memory_signals if isinstance(memory_signals, dict) else {}

    target_cal = _safe_float(daily.get("target_calories") or plan.get("target_calories"), 0.0)
    target_protein = _safe_float(daily.get("target_protein_g") or plan.get("target_protein_g"), 0.0)
    consumed_cal = _safe_float(daily.get("consumed_calories"), 0.0)
    consumed_protein = _safe_float(daily.get("consumed_protein_g"), 0.0)

    remaining_cal = max(0.0, target_cal - consumed_cal) if target_cal > 0 else 0.0
    remaining_protein = max(0.0, target_protein - consumed_protein) if target_protein > 0 else 0.0

    goal_type = _safe_str(plan.get("goal_type") or "fat_loss").lower()

    headline = "Good runway for today."
    action = "Keep next meal protein-first and log it."
    risk_flags: List[str] = []
    wins: List[str] = []
    blockers: List[str] = []

    if target_cal > 0:
        cal_ratio = consumed_cal / max(1.0, target_cal)
    else:
        cal_ratio = 0.0
    if target_protein > 0:
        protein_ratio = consumed_protein / max(1.0, target_protein)
    else:
        protein_ratio = 0.0

    if cal_ratio >= 0.9 and protein_ratio < 0.7:
        headline = "Calories are high but protein is still low."
        action = "Make tonight’s meal lean-protein heavy and skip calorie-dense extras."
        risk_flags.append("protein_behind_high_calories")
        blockers.append("Low protein before calories filled up.")
    elif remaining_protein >= 60:
        headline = "Protein gap is the main lever today."
        action = "Plan 1–2 strong protein meals from now to hit the target."
        risk_flags.append("protein_gap")
    elif remaining_cal <= 300 and goal_type == "fat_loss":
        headline = "Calories are getting tight."
        action = "Keep the next meal lighter and skip late-night snacking."
        risk_flags.append("late_night_risk")
    elif cal_ratio <= 0.4 and protein_ratio >= 0.35:
        headline = "Strong start on protein."
        action = "Repeat this pattern at dinner to lock in the day."
        wins.append("Good early-day protein coverage.")

    if mem.get("late_night_snacking"):
        risk_flags.append("late_night_snacking_pattern")
    if mem.get("weekend_overeating"):
        risk_flags.append("weekend_overeating_pattern")
    if mem.get("misses_protein_on_rest_days"):
        risk_flags.append("rest_day_protein_risk")

    coach_focus = "protein_first" if "protein_gap" in risk_flags or "rest_day_protein_risk" in risk_flags else "calorie_drift"

    return {
        "date": _safe_str(daily.get("date") or daily.get("day")),
        "goal_type": goal_type,
        "targets": {
            "calories": round(target_cal, 1),
            "protein_g": round(target_protein, 1),
        },
        "consumed": {
            "calories": round(consumed_cal, 1),
            "protein_g": round(consumed_protein, 1),
        },
        "remaining": {
            "calories": round(remaining_cal, 1),
            "protein_g": round(remaining_protein, 1),
        },
        "coach_focus": coach_focus,
        "headline": headline,
        "one_action_today": action,
        "risk_flags": risk_flags,
        "wins": wins,
        "blockers": blockers,
        "version": GOAL_COACH_VERSION,
    }


# Action types for CTA mapping (no LLM)
ACTION_OPEN_HEALTHY_NEARBY = "open_healthy_nearby"
ACTION_OPEN_SCAN_CAMERA = "open_scan_camera"
ACTION_OPEN_SUPPLEMENT_SCAN = "open_supplement_scan"
ACTION_OPEN_DAILY_SUMMARY = "open_daily_summary"
ACTION_OPEN_GOAL_PLAN = "open_goal_plan"


def _action(
    action_type: str,
    label: str,
    reason: str,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "action_type": action_type,
        "label": label,
        "reason": reason,
    }
    if context:
        out["context"] = context
    return out


def build_daily_suggested_actions(
    state: Dict[str, Any],
    current_hour_local: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Deterministic mapping from daily coach state to one primary and optional secondary action.
    current_hour_local: 0-23 in user's local time; if None, assume daytime (12).
    """
    goal_type = _safe_str(state.get("goal_type") or "fat_loss").lower()
    remaining = state.get("remaining") or {}
    remaining_cal = _safe_float(remaining.get("calories"), 0.0)
    remaining_protein = _safe_float(remaining.get("protein_g"), 0.0)
    consumed_cal = _safe_float((state.get("consumed") or {}).get("calories"), 0.0)
    risk_flags = list(state.get("risk_flags") or [])
    coach_focus = _safe_str(state.get("coach_focus", ""))

    hour = current_hour_local if current_hour_local is not None else 12
    daytime = 6 <= hour <= 18
    meal_time = 7 <= hour <= 21

    context = {
        "goal": goal_type,
        "remaining_protein_g": int(remaining_protein),
        "remaining_calories": int(remaining_cal),
    }

    primary: Optional[Dict[str, Any]] = None
    secondary: Optional[Dict[str, Any]] = None

    # Calories already high + protein still low → check summary or lighter nearby
    if "protein_behind_high_calories" in risk_flags or (remaining_cal <= 350 and goal_type == "fat_loss"):
        primary = _action(
            ACTION_OPEN_DAILY_SUMMARY,
            "Check today's totals",
            "Calories are tight; see where you stand.",
            context,
        )
        if remaining_protein >= 25 and daytime:
            secondary = _action(
                ACTION_OPEN_HEALTHY_NEARBY,
                "Find a lighter high-protein option",
                "Protein still matters with limited calories.",
                context,
            )
    # Protein gap + daytime → find high-protein meal nearby
    elif (coach_focus == "protein_first" or "protein_gap" in risk_flags) and remaining_protein >= 35 and daytime:
        primary = _action(
            ACTION_OPEN_HEALTHY_NEARBY,
            "Find a high-protein meal nearby",
            "Protein is behind today.",
            context,
        )
        if remaining_protein >= 40:
            secondary = _action(
                ACTION_OPEN_SUPPLEMENT_SCAN,
                "Add protein (e.g. shake)",
                "Quick way to close the protein gap.",
                context,
            )
    # Very little logged so far and meal time → log meal
    elif consumed_cal < 400 and meal_time:
        primary = _action(
            ACTION_OPEN_SCAN_CAMERA,
            "Scan your meal now",
            "Take a quick photo — we'll analyze it right after.",
            context,
        )
    # Late-night risk → lighter option or summary
    elif "late_night_risk" in risk_flags or "late_night_snacking_pattern" in risk_flags:
        primary = _action(
            ACTION_OPEN_DAILY_SUMMARY,
            "Check today's totals",
            "Keep the rest of the day light.",
            context,
        )
    # Default: log next meal or find nearby
    else:
        primary = _action(
            ACTION_OPEN_SCAN_CAMERA,
            "Scan your next meal now",
            "Quick photo → instant analysis → you stay on track.",
            context,
        )
        if daytime and remaining_protein >= 30:
            secondary = _action(
                ACTION_OPEN_HEALTHY_NEARBY,
                "Find a better option nearby",
                state.get("headline") or "See what fits your plan.",
                context,
            )

    out: Dict[str, Any] = {"primary_action": primary}
    if secondary:
        out["secondary_action"] = secondary
    return out


def build_coach_connection_line(state: Dict[str, Any], wins_streaks: Dict[str, Any]) -> str:
    """
    Warm, deterministic check-in line for home / daily card (empathy + momentum, no LLM).
    """
    st = state if isinstance(state, dict) else {}
    ws = wins_streaks if isinstance(wins_streaks, dict) else {}
    protein_streak = _safe_int(ws.get("protein_streak_days"), 0)
    logging_streak = _safe_int(ws.get("logging_streak_days"), 0)
    wins = list(st.get("wins") or [])
    risk = list(st.get("risk_flags") or [])

    if protein_streak >= 5:
        return (
            f"You've put together {protein_streak} strong protein days in a row—that's not luck; "
            "it's a habit forming."
        )
    if protein_streak >= 3:
        return (
            "You're stacking solid protein days. Keep riding what's working; your coach is paying attention."
        )
    if logging_streak >= 5:
        return (
            f"{logging_streak} days logging in a row shows real commitment. "
            "Consistency is what moves the needle."
        )
    if logging_streak >= 3:
        return "Showing up and logging matters—your pattern is getting clearer every day."
    if wins:
        return "Nice work on today's early wins. Small choices strung together are how change sticks."
    if "protein_gap" in risk or "protein_behind_high_calories" in risk:
        return (
            "Today's a bit uneven—that happens to everyone. "
            "One deliberate, protein-forward meal can reset how the day feels."
        )
    if "late_night_risk" in risk or "late_night_snacking_pattern" in risk:
        return (
            "Evenings are often the hardest window; you're not alone there. "
            "Keep the next bite simple and lighter if you can."
        )
    if "weekend_overeating_pattern" in risk:
        return "Weekends can throw anyone off. Monday is a fresh lane—one planned meal gets you back in rhythm."
    return (
        "Glad you're here. Steady beats perfect: focus on the next right meal, "
        "and check in when you can—we're tracking the trend with you."
    )


def build_progress_reminder(
    *,
    day_iso: str,
    week_start_iso: str,
    journey_summary: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    Nudge weight or progress photo when journey data suggests the user hasn't checked in on paper.
    Deterministic; optional dict for mobile banner + scroll-to-progress.
    """
    js = journey_summary if isinstance(journey_summary, dict) else {}
    today = _parse_day_iso(day_iso)
    week_key = (week_start_iso or "")[:10]

    latest_w = js.get("latest_weight")
    wday_raw = (latest_w or {}).get("day") if isinstance(latest_w, dict) else None
    days_since_weight: Optional[int] = None
    if today and wday_raw:
        wd = _parse_day_iso(str(wday_raw))
        if wd:
            days_since_weight = max(0, (today - wd).days)

    latest_photo = js.get("latest_photo")
    photo_week = (latest_photo or {}).get("week_start") if isinstance(latest_photo, dict) else None
    has_photo_this_week = bool(photo_week and str(photo_week)[:10] == week_key)

    check_ins = _safe_int(js.get("check_ins_count"), 0)
    weight_count = _safe_int(js.get("weight_entries_count"), 0)

    if weight_count == 0 and check_ins >= 4:
        return {
            "kind": "weight",
            "priority": "normal",
            "message": (
                "When you're ready, add a starting weight on Home → Progress. "
                "It gives your coach a baseline to compare over time."
            ),
            "cta_label": "Go to Progress",
        }

    if days_since_weight is not None and days_since_weight >= 10:
        return {
            "kind": "weight",
            "priority": "high",
            "message": (
                f"It's been {days_since_weight} days since your last weigh-in. "
                "A quick log keeps the trend honest—no judgment, just signal."
            ),
            "cta_label": "Log weight",
        }
    if days_since_weight is not None and days_since_weight >= 5:
        return {
            "kind": "weight",
            "priority": "normal",
            "message": (
                "Quick nudge: update your weight when you can so progress stays grounded in real numbers."
            ),
            "cta_label": "Log weight",
        }

    # Progress-photo nudge disabled — mobile app doesn't have a progress-photo
    # feature yet. Re-enable when PlaceDetailSheet-style photo capture + storage
    # + coach comparison is built. See memory: project_coach_photo_gap.md.
    # if today and not has_photo_this_week and today.weekday() >= 2:
    #     return {
    #         "kind": "photo",
    #         "priority": "normal",
    #         "message": (
    #             "Add a progress photo this week—same spot and lighting makes before/afters easier to trust."
    #         ),
    #         "cta_label": "Compare photos",
    #     }

    return None


def build_meal_log_encouragement(state: Dict[str, Any], wins_streaks: Dict[str, Any]) -> str:
    """Short line after a meal scan when Goal Coach is active (deterministic)."""
    st = state if isinstance(state, dict) else {}
    ws = wins_streaks if isinstance(wins_streaks, dict) else {}
    daily_win = ws.get("daily_win") if isinstance(ws.get("daily_win"), dict) else {}
    protein_hit = bool(daily_win.get("protein_hit"))
    kcal_ok = bool(daily_win.get("kcal_in_range"))
    ps = _safe_int(ws.get("protein_streak_days"), 0)
    ls = _safe_int(ws.get("logging_streak_days"), 0)
    risk = list(st.get("risk_flags") or [])

    if protein_hit and kcal_ok:
        return "That meal keeps calories and protein aligned with today—exactly the kind of day we're building."
    if protein_hit:
        return "Solid protein move—this scan helps protect muscle while you work the plan."
    if ps >= 3:
        return f"Logged—your {ps}-day protein streak is still in play. Keep stacking."
    if ls >= 3:
        return f"Another meal on the books. {ls} days logging in a row is real momentum."
    if "protein_gap" in risk or "protein_behind_high_calories" in risk:
        return "Thanks for logging—seeing the day clearly is how we tighten the next meal together."
    return "Thanks for logging this one—each scan is a check-in with your coach, not just the numbers."


def build_weekly_next_step_action(review: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Map weekly review to one next-step action for the app.
    """
    if not review or not isinstance(review, dict):
        return None
    next_focus = review.get("next_week_focus") or {}
    headline = _safe_str(next_focus.get("headline", ""))
    supporting = _safe_str(next_focus.get("supporting_text", ""))
    main_bottleneck = _safe_str(review.get("main_bottleneck", ""))
    summary = review.get("summary") or {}
    days_tracked = _safe_int(summary.get("days_tracked"), 0)
    days_under_protein = _safe_int(summary.get("days_under_protein"), 0)
    days_over_target = _safe_int(summary.get("days_over_target"), 0)

    goal_type = _safe_str(review.get("goal_type", "fat_loss")).lower()
    context: Dict[str, Any] = {"goal": goal_type}

    # Focus on logging consistency
    if days_tracked < 5 or "logging" in headline.lower() or "log" in supporting.lower():
        return _action(
            ACTION_OPEN_SCAN_CAMERA,
            "Log meals more consistently this week",
            supporting or "More logs help your coach.",
            context,
        )
    # Protein focus
    if days_under_protein >= 2 or "protein" in headline.lower() or "protein" in main_bottleneck.lower():
        return _action(
            ACTION_OPEN_HEALTHY_NEARBY,
            "Improve protein choices nearby",
            supporting or "Find higher-protein options for next week.",
            context,
        )
    # Calorie/dinner focus
    if days_over_target >= 2 or "dinner" in headline.lower() or "calories" in main_bottleneck.lower():
        return _action(
            ACTION_OPEN_HEALTHY_NEARBY,
            "Plan lighter dinner options nearby",
            supporting or "See options that fit your plan.",
            context,
        )
    # Generic next week
    if headline or supporting:
        return _action(
            ACTION_OPEN_GOAL_PLAN,
            headline or "Plan next week",
            supporting or "Stay on track.",
            context,
        )
    return _action(
        ACTION_OPEN_SCAN_CAMERA,
        "Log meals more consistently this week",
        "Consistency drives results.",
        context,
    )


def build_weekly_review(
    plan: Dict[str, Any],
    days: List[Dict[str, Any]],
    memory_signals: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Wrap existing weekly_coach signals into goal-coach specific weekly review.
    """
    goal_type = _safe_str(plan.get("goal_type") or "fat_loss").lower()
    week_payload = build_weekly_coach_payload(days=days, choices=None, goal=goal_type, cut_mode=(goal_type == "fat_loss"))
    summary = week_payload.get("week_summary") or {}

    days_tracked = _safe_int(summary.get("days_tracked") or 0, 0)
    days_on_track = _safe_int(summary.get("days_on_track") or 0, 0)
    days_over_target = _safe_int(summary.get("days_over_target") or 0, 0)
    days_under_protein = _safe_int(summary.get("days_under_protein") or 0, 0)

    adherence = int(round(100.0 * (days_on_track / max(1, days_tracked))))
    risk_components = (days_over_target * 12) + (days_under_protein * 8)
    risk_score = max(0, min(100, risk_components))
    resilience_score = max(0, min(100, 100 - risk_score // 2))

    mem = memory_signals if isinstance(memory_signals, dict) else {}
    mem_flags: List[str] = []
    for key in ["late_night_snacking", "misses_protein_on_rest_days", "weekend_overeating", "better_with_high_protein_breakfast"]:
        if mem.get(key):
            mem_flags.append(key)

    if adherence >= 70 and risk_score <= 35:
        main_win = "You stayed close to calories on most tracked days."
    elif days_on_track >= max(2, days_tracked // 2):
        main_win = "Consistency improved versus recent weeks."
    else:
        main_win = "You kept some structure even on tougher days."

    if days_over_target >= max(2, days_tracked // 2):
        main_bottleneck = "Calories drifted high on several days."
    elif days_under_protein >= max(2, days_tracked // 2):
        main_bottleneck = "Protein dipped on too many days."
    else:
        main_bottleneck = "Drift showed up mostly on unplanned meals or snacks."

    next_focus = week_payload.get("next_week_focus") or {}
    projection_score = max(0, min(100, adherence - (risk_score // 3)))

    return {
        "goal_type": goal_type,
        "headline": week_payload.get("headline"),
        "supporting_text": week_payload.get("supporting_text"),
        "adherence_score": adherence,
        "resilience_score": resilience_score,
        "risk_score": risk_score,
        "projection_score": projection_score,
        "main_win": main_win,
        "main_bottleneck": main_bottleneck,
        "next_week_focus": next_focus,
        "habit_memory_flags": mem_flags,
        "summary": summary,
        "coach_version": GOAL_COACH_VERSION,
    }

