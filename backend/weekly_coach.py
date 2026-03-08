from __future__ import annotations

import datetime as dt
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple


WEEKLY_COACH_VERSION = "v1"


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _safe_str(value: Any) -> str:
    return str(value or "").strip()


def _parse_day(day_iso: str) -> Optional[dt.date]:
    raw = _safe_str(day_iso)
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except Exception:
        return None


def _weekday_name(day_iso: str) -> str:
    parsed = _parse_day(day_iso)
    if not parsed:
        return ""
    return parsed.strftime("%A")


def _normalized_days(days: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in (days or []):
        if not isinstance(row, dict):
            continue
        day = _safe_str(row.get("date") or row.get("day"))
        consumed_cal = _safe_optional_float(row.get("consumed_calories"))
        target_cal = _safe_optional_float(row.get("target_calories"))
        consumed_protein = _safe_optional_float(row.get("consumed_protein_g"))
        target_protein = _safe_optional_float(row.get("target_protein_g"))

        if consumed_cal is None and consumed_protein is None:
            continue

        out.append(
            {
                "date": day,
                "weekday": _weekday_name(day),
                "consumed_calories": consumed_cal,
                "target_calories": target_cal,
                "consumed_protein_g": consumed_protein,
                "target_protein_g": target_protein,
                "lunch_calories": _safe_optional_float(row.get("lunch_calories")),
                "dinner_calories": _safe_optional_float(row.get("dinner_calories")),
                "lunch_protein_g": _safe_optional_float(row.get("lunch_protein_g")),
                "dinner_protein_g": _safe_optional_float(row.get("dinner_protein_g")),
            }
        )
    return out


def build_weekly_progress_summary(days: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = _normalized_days(days)
    if not rows:
        return {
            "days_tracked": 0,
            "days_on_track": 0,
            "days_over_target": 0,
            "days_under_protein": 0,
            "average_daily_protein_g": 0,
            "average_daily_calories": 0,
        }

    days_on_track = 0
    days_over_target = 0
    days_under_protein = 0

    consumed_calories_vals: List[float] = []
    consumed_protein_vals: List[float] = []

    for row in rows:
        cal = row.get("consumed_calories")
        cal_target = row.get("target_calories")
        protein = row.get("consumed_protein_g")
        protein_target = row.get("target_protein_g")

        if cal is not None:
            consumed_calories_vals.append(float(cal))
        if protein is not None:
            consumed_protein_vals.append(float(protein))

        cal_on_track = (
            cal is not None and cal_target is not None and cal <= (float(cal_target) * 1.05)
        )
        protein_on_track = (
            protein is None
            or protein_target is None
            or protein >= (float(protein_target) * 0.85)
        )
        if cal_on_track and protein_on_track:
            days_on_track += 1

        if cal is not None and cal_target is not None and cal > (float(cal_target) * 1.05):
            days_over_target += 1

        if protein is not None and protein_target is not None and protein < (float(protein_target) * 0.85):
            days_under_protein += 1

    avg_cal = round(sum(consumed_calories_vals) / max(1, len(consumed_calories_vals)), 1)
    avg_protein = round(sum(consumed_protein_vals) / max(1, len(consumed_protein_vals)), 1)

    return {
        "days_tracked": len(rows),
        "days_on_track": int(max(0, days_on_track)),
        "days_over_target": int(max(0, days_over_target)),
        "days_under_protein": int(max(0, days_under_protein)),
        "average_daily_protein_g": avg_protein,
        "average_daily_calories": avg_cal,
    }


def _meal_window_signal(days: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    rows = _normalized_days(days)
    lunch_cal: List[float] = []
    dinner_cal: List[float] = []
    lunch_protein: List[float] = []
    dinner_protein: List[float] = []

    for row in rows:
        if row.get("lunch_calories") is not None:
            lunch_cal.append(float(row["lunch_calories"]))
        if row.get("dinner_calories") is not None:
            dinner_cal.append(float(row["dinner_calories"]))
        if row.get("lunch_protein_g") is not None:
            lunch_protein.append(float(row["lunch_protein_g"]))
        if row.get("dinner_protein_g") is not None:
            dinner_protein.append(float(row["dinner_protein_g"]))

    if not lunch_cal or not dinner_cal:
        return None, None

    avg_lunch_cal = sum(lunch_cal) / max(1, len(lunch_cal))
    avg_dinner_cal = sum(dinner_cal) / max(1, len(dinner_cal))
    avg_lunch_protein = sum(lunch_protein) / max(1, len(lunch_protein)) if lunch_protein else 0.0
    avg_dinner_protein = sum(dinner_protein) / max(1, len(dinner_protein)) if dinner_protein else 0.0

    lunch_density = avg_lunch_protein / max(1.0, avg_lunch_cal)
    dinner_density = avg_dinner_protein / max(1.0, avg_dinner_cal)

    positive = None
    warning = None

    if lunch_density >= (dinner_density + 0.01) and avg_lunch_cal <= (avg_dinner_cal + 80.0):
        positive = {
            "type": "positive",
            "title": "Lunch decisions were strong",
            "text": "Your lunch choices were more macro-friendly than dinner choices.",
        }

    if avg_dinner_cal >= (avg_lunch_cal + 160.0):
        warning = {
            "type": "warning",
            "title": "Dinner is where calories drift",
            "text": "Your evening meals trend heavier than lunch across the week.",
        }

    return positive, warning


def _risk_day_signal(days: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = _normalized_days(days)
    if not rows:
        return None

    weekday_over = defaultdict(int)
    for row in rows:
        cal = row.get("consumed_calories")
        target = row.get("target_calories")
        weekday = _safe_str(row.get("weekday"))
        if not weekday or cal is None or target is None:
            continue
        if cal > (float(target) * 1.08):
            weekday_over[weekday] += 1

    if not weekday_over:
        return None

    risk_day = sorted(weekday_over.items(), key=lambda item: item[1], reverse=True)[0][0]
    return {
        "type": "warning",
        "title": f"Calories drift on {risk_day}s",
        "text": f"Your higher-calorie pattern appears most often on {risk_day}s.",
    }


def _weekday_protein_signal(days: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    rows = _normalized_days(days)
    if not rows:
        return None

    weekdays = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday"}
    tracked_weekdays = 0
    weekday_under = 0

    for row in rows:
        weekday = _safe_str(row.get("weekday"))
        if weekday not in weekdays:
            continue
        consumed = row.get("consumed_protein_g")
        target = row.get("target_protein_g")
        if consumed is None or target is None:
            continue
        tracked_weekdays += 1
        if float(consumed) < (float(target) * 0.85):
            weekday_under += 1

    if tracked_weekdays >= 3 and weekday_under >= max(2, int(round(tracked_weekdays * 0.6))):
        return {
            "type": "warning",
            "title": "Protein dipped on weekdays",
            "text": "You were under protein target on most weekday meals.",
        }

    return None


def build_habit_insights(days: List[Dict[str, Any]], week_summary: Dict[str, Any]) -> List[Dict[str, str]]:
    tracked = int(_safe_float(week_summary.get("days_tracked"), 0) or 0)
    on_track = int(_safe_float(week_summary.get("days_on_track"), 0) or 0)
    under_protein = int(_safe_float(week_summary.get("days_under_protein"), 0) or 0)

    if tracked < 3:
        return [
            {
                "type": "info",
                "title": "Still learning your pattern",
                "text": "Keep scanning meals this week for sharper weekly coaching.",
            }
        ]

    insights: List[Dict[str, str]] = []

    if on_track >= max(2, int(round(tracked * 0.6))):
        insights.append(
            {
                "type": "positive",
                "title": "Consistency improved this week",
                "text": "You stayed close to calories on most tracked days.",
            }
        )

    if under_protein >= max(2, int(round(tracked * 0.5))):
        weekday_protein = _weekday_protein_signal(days)
        if weekday_protein:
            insights.append(weekday_protein)
        else:
            insights.append(
                {
                    "type": "warning",
                    "title": "Protein dipped this week",
                    "text": "You were under your protein target on several days.",
                }
            )

    lunch_positive, dinner_warning = _meal_window_signal(days)
    if lunch_positive:
        insights.append(lunch_positive)
    if dinner_warning:
        insights.append(dinner_warning)

    risk_day = _risk_day_signal(days)
    if risk_day:
        insights.append(risk_day)

    if not insights:
        insights.append(
            {
                "type": "positive",
                "title": "Momentum is steady",
                "text": "Your week was mostly balanced with no major drift pattern.",
            }
        )

    return insights[:3]


def build_best_choices_this_week(choices: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in (choices or []):
        if not isinstance(row, dict):
            continue
        place_name = _safe_str(row.get("place_name"))
        order_name = _safe_str(row.get("recommended_order") or row.get("item"))
        if not place_name or not order_name:
            continue
        key = (place_name.lower(), order_name.lower())
        bucket = grouped.setdefault(
            key,
            {
                "place_name": place_name,
                "recommended_order": order_name,
                "count": 0,
                "fit_hits": 0,
                "health_score_sum": 0.0,
                "health_score_n": 0,
                "why_it_helped": _safe_str(row.get("why_it_helped")),
            },
        )
        bucket["count"] += 1
        if bool(row.get("fit_for_today")):
            bucket["fit_hits"] += 1
        hs = _safe_optional_float(row.get("health_score"))
        if hs is not None:
            bucket["health_score_sum"] += float(hs)
            bucket["health_score_n"] += 1
        if not bucket["why_it_helped"]:
            bucket["why_it_helped"] = _safe_str(row.get("why_it_helped"))

    ranked: List[Dict[str, Any]] = []
    for row in grouped.values():
        avg_health = (
            row["health_score_sum"] / max(1, row["health_score_n"])
            if row["health_score_n"] > 0
            else 70.0
        )
        score = (row["count"] * 1.5) + row["fit_hits"] + (avg_health / 100.0)
        why = _safe_str(row.get("why_it_helped"))
        if not why:
            why = (
                "Strong protein with better calorie control."
                if row["fit_hits"] >= max(1, row["count"] // 2)
                else "More macro-friendly than typical choices."
            )
        ranked.append(
            {
                "place_name": row["place_name"],
                "recommended_order": row["recommended_order"],
                "why_it_helped": why,
                "_score": score,
            }
        )

    ranked.sort(key=lambda item: float(_safe_float(item.get("_score"), 0.0) or 0.0), reverse=True)
    out = []
    for row in ranked[:2]:
        clean = dict(row)
        clean.pop("_score", None)
        out.append(clean)
    return out


def build_next_week_focus(week_summary: Dict[str, Any]) -> Dict[str, str]:
    tracked = int(_safe_float(week_summary.get("days_tracked"), 0) or 0)
    over_target = int(_safe_float(week_summary.get("days_over_target"), 0) or 0)
    under_protein = int(_safe_float(week_summary.get("days_under_protein"), 0) or 0)

    if tracked < 4:
        return {
            "headline": "Focus on logging 5 days next week.",
            "supporting_text": "More consistent logging will make your coach insights much sharper.",
        }
    if under_protein >= max(2, tracked // 2):
        return {
            "headline": "Focus on one more protein-heavy meal each weekday.",
            "supporting_text": "That makes it easier to hit protein without overshooting calories.",
        }
    if over_target >= max(2, tracked // 2):
        return {
            "headline": "Focus on lighter dinners next week.",
            "supporting_text": "A tighter evening meal keeps your weekly calories more stable.",
        }
    return {
        "headline": "Keep repeating your strongest meal pattern.",
        "supporting_text": "Stay consistent with the choices that kept you on track this week.",
    }


def build_weekly_coach_payload(
    *,
    days: List[Dict[str, Any]],
    choices: Optional[List[Dict[str, Any]]] = None,
    goal: str = "",
    cut_mode: bool = False,
) -> Dict[str, Any]:
    week_summary = build_weekly_progress_summary(days)
    tracked = int(_safe_float(week_summary.get("days_tracked"), 0) or 0)
    on_track = int(_safe_float(week_summary.get("days_on_track"), 0) or 0)
    under_protein = int(_safe_float(week_summary.get("days_under_protein"), 0) or 0)

    if tracked < 3:
        headline = "Still learning your weekly pattern."
        supporting = "Keep scanning meals and using nearby decisions for stronger weekly insights."
    else:
        on_track_ratio = on_track / max(1, tracked)
        protein_ratio = under_protein / max(1, tracked)
        if on_track_ratio >= 0.6 and protein_ratio <= 0.4:
            headline = "Solid week overall."
            supporting = (
                f"You stayed close to calories on {on_track} of the last {tracked} tracked days."
            )
        elif protein_ratio > 0.5:
            headline = "Weekly consistency is improving."
            supporting = (
                "Calories were often close, but protein dipped on several days."
            )
        else:
            headline = "Decent week with room to improve."
            supporting = (
                "A tighter dinner strategy can improve next week's consistency."
            )

    goal_token = _safe_str(goal).lower()
    if (goal_token == "fat_loss" or bool(cut_mode)) and tracked >= 3 and under_protein >= 2:
        supporting = supporting + " Add one more lean protein meal on low-protein days."

    habit_insights = build_habit_insights(days, week_summary)
    best_choices = build_best_choices_this_week(choices or [])
    next_week_focus = build_next_week_focus(week_summary)

    out = {
        "headline": headline,
        "supporting_text": supporting,
        "week_summary": {
            "days_on_track": week_summary.get("days_on_track", 0),
            "days_over_target": week_summary.get("days_over_target", 0),
            "average_daily_protein_g": week_summary.get("average_daily_protein_g", 0),
            "average_daily_calories": week_summary.get("average_daily_calories", 0),
            "days_tracked": week_summary.get("days_tracked", 0),
            "days_under_protein": week_summary.get("days_under_protein", 0),
        },
        "habit_insights": habit_insights,
        "next_week_focus": next_week_focus,
        "coach_version": WEEKLY_COACH_VERSION,
    }

    if best_choices:
        out["best_choices_this_week"] = best_choices

    return out
