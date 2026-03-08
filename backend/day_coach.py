from __future__ import annotations

from typing import Any, Dict, List, Optional

from llm_coach_phrasing import maybe_rephrase_coach_message


DAY_COACH_VERSION = "v1"


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


def _round_opt(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 1)


def _resolve_macro_progress(
    *,
    target_calories: Any = None,
    consumed_calories: Any = None,
    remaining_calories: Any = None,
    target_protein_g: Any = None,
    consumed_protein_g: Any = None,
    remaining_protein_g: Any = None,
) -> Dict[str, Optional[float]]:
    target_cal = _safe_optional_float(target_calories)
    consumed_cal = _safe_optional_float(consumed_calories)
    remain_cal = _safe_optional_float(remaining_calories)

    target_protein = _safe_optional_float(target_protein_g)
    consumed_protein = _safe_optional_float(consumed_protein_g)
    remain_protein = _safe_optional_float(remaining_protein_g)

    if target_cal is None and consumed_cal is not None and remain_cal is not None:
        target_cal = consumed_cal + remain_cal
    if consumed_cal is None and target_cal is not None and remain_cal is not None:
        consumed_cal = max(0.0, target_cal - remain_cal)
    if remain_cal is None and target_cal is not None and consumed_cal is not None:
        remain_cal = max(0.0, target_cal - consumed_cal)

    if target_protein is None and consumed_protein is not None and remain_protein is not None:
        target_protein = consumed_protein + remain_protein
    if consumed_protein is None and target_protein is not None and remain_protein is not None:
        consumed_protein = max(0.0, target_protein - remain_protein)
    if remain_protein is None and target_protein is not None and consumed_protein is not None:
        remain_protein = max(0.0, target_protein - consumed_protein)

    return {
        "target_calories": _round_opt(target_cal),
        "consumed_calories": _round_opt(consumed_cal),
        "remaining_calories": _round_opt(remain_cal),
        "target_protein_g": _round_opt(target_protein),
        "consumed_protein_g": _round_opt(consumed_protein),
        "remaining_protein_g": _round_opt(remain_protein),
    }


def build_day_coach_summary(
    *,
    target_calories: Any = None,
    consumed_calories: Any = None,
    remaining_calories: Any = None,
    target_protein_g: Any = None,
    consumed_protein_g: Any = None,
    remaining_protein_g: Any = None,
    goal: str = "",
    cut_mode: bool = False,
) -> Dict[str, Any]:
    progress = _resolve_macro_progress(
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        remaining_calories=remaining_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        remaining_protein_g=remaining_protein_g,
    )

    remain_cal = progress.get("remaining_calories")
    remain_protein = progress.get("remaining_protein_g")
    consumed_cal = progress.get("consumed_calories")
    target_cal = progress.get("target_calories")
    consumed_protein = progress.get("consumed_protein_g")
    target_protein = progress.get("target_protein_g")

    headline = "You're on track right now."
    supporting_text = "Keep your next meal protein-first and macro-friendly."

    if remain_cal is not None and remain_cal <= 350:
        headline = "Calories are getting tight."
        supporting_text = "Keep the next meal lighter and skip calorie-dense sides."
    elif remain_protein is not None and remain_protein >= 70:
        headline = "Good start today."
        supporting_text = f"You still need about {int(round(remain_protein))}g protein by tonight."
    elif remain_protein is not None and remain_protein >= 35:
        headline = "Solid momentum so far."
        supporting_text = "One strong protein meal keeps the day on track."
    elif remain_cal is not None and remain_cal >= 1000:
        headline = "Good runway for a smart lunch."
        supporting_text = "Use this window for a high-protein meal with controlled calories."

    goal_token = str(goal or "").strip().lower()
    if (goal_token == "fat_loss" or bool(cut_mode)) and remain_cal is not None and remain_cal < 700:
        supporting_text = "Stay cut-friendly now: lean protein, lighter sides, and simple sauces."

    if (
        target_cal is not None
        and consumed_cal is not None
        and target_protein is not None
        and consumed_protein is not None
        and target_cal > 0
    ):
        calorie_progress = consumed_cal / max(1.0, target_cal)
        protein_progress = consumed_protein / max(1.0, target_protein)
        if calorie_progress <= 0.45 and protein_progress >= 0.35:
            headline = "Good start today."
            if remain_protein is not None and remain_protein > 0:
                supporting_text = f"Protein is moving well. You still need about {int(round(remain_protein))}g by tonight."

    phrased = maybe_rephrase_coach_message(
        headline=headline,
        supporting_text=supporting_text,
        context={
            "tone": "encouraging",
            "goal": str(goal or "").strip().lower(),
            "cut_mode": bool(cut_mode),
        },
    )

    return {
        "headline": str(phrased.get("headline") or headline),
        "supporting_text": str(phrased.get("supporting_text") or supporting_text),
        "progress": progress,
        "phrasing_method": str(phrased.get("phrasing_method") or "deterministic"),
        "phrasing_version": str(phrased.get("phrasing_version") or "v1"),
    }


def build_next_meal_guidance(
    *,
    top_recommendation: Optional[Dict[str, Any]] = None,
    remaining_calories: Any = None,
    remaining_protein_g: Any = None,
    goal: str = "",
    cut_mode: bool = False,
) -> Optional[Dict[str, Any]]:
    rec = top_recommendation if isinstance(top_recommendation, dict) else {}
    place_name = str(rec.get("place_name") or "").strip()
    if not place_name:
        return None

    est_cal = int(max(0, _safe_float(rec.get("estimated_calories"), 0.0) or 0.0))
    est_protein = int(max(0, _safe_float(rec.get("estimated_protein_g"), 0.0) or 0.0))
    decision_token = str(rec.get("decision_today") or "").strip().upper()
    if decision_token not in {"YES", "MAYBE", "NO"}:
        fit_flag = rec.get("fit_for_today")
        decision_token = "YES" if fit_flag is True else "NO" if fit_flag is False else "MAYBE"

    remain_cal = _safe_optional_float(remaining_calories)
    remain_protein = _safe_optional_float(remaining_protein_g)
    goal_token = str(goal or "").strip().lower()

    supporting_text = "A strong nearby pick to stay consistent today."
    if decision_token == "NO":
        supporting_text = "Harder to fit today unless you keep the order very light."
    elif decision_token == "MAYBE":
        supporting_text = "Can work today if you keep swaps clean and skip heavy extras."
    elif remain_protein is not None and remain_protein >= 35 and est_protein >= 28:
        supporting_text = "A high-protein lunch helps close your gap without overshooting calories."
    elif remain_cal is not None and est_cal > 0 and est_cal > remain_cal:
        supporting_text = "Portion-control this order to stay within your calorie target."
    elif goal_token == "fat_loss" or bool(cut_mode):
        supporting_text = "Strong cut-friendly pick with better calorie control."

    return {
        "headline": "Best lunch near you",
        "supporting_text": supporting_text,
        "recommended_place_name": place_name,
        "recommended_order": str(rec.get("recommended_order") or "Smart high-protein order").strip(),
        "estimated_calories": est_cal,
        "estimated_protein_g": est_protein,
    }


def build_evening_guidance(
    *,
    remaining_calories: Any = None,
    remaining_protein_g: Any = None,
    current_hour: Any = None,
    cut_mode: bool = False,
    goal: str = "",
) -> Optional[Dict[str, Any]]:
    remain_cal = _safe_optional_float(remaining_calories)
    remain_protein = _safe_optional_float(remaining_protein_g)
    hour = _safe_optional_float(current_hour)
    goal_token = str(goal or "").strip().lower()

    if remain_cal is None and remain_protein is None:
        return None

    if remain_cal is not None and remain_cal <= 350:
        return {
            "headline": "Keep dinner lighter tonight.",
            "supporting_text": "You'll stay on track more easily if you avoid calorie-dense sides.",
        }

    if remain_protein is not None and remain_protein >= 35 and (
        (hour is not None and hour >= 15) or (remain_cal is not None and remain_cal <= 900)
    ):
        return {
            "headline": "Use dinner to close your protein gap.",
            "supporting_text": "Lean protein first, then keep sauces and sides controlled.",
        }

    if hour is not None and hour >= 18:
        if goal_token == "fat_loss" or bool(cut_mode):
            return {
                "headline": "Finish with a cut-friendly dinner.",
                "supporting_text": "Keep portions tight and prioritize protein.",
            }
        return {
            "headline": "Finish the day with a balanced dinner.",
            "supporting_text": "Lean protein plus a lighter side keeps momentum steady.",
        }

    return None


def build_end_of_day_feedback(
    *,
    target_calories: Any = None,
    consumed_calories: Any = None,
    target_protein_g: Any = None,
    consumed_protein_g: Any = None,
    remaining_calories: Any = None,
    remaining_protein_g: Any = None,
    current_hour: Any = None,
) -> Optional[Dict[str, Any]]:
    progress = _resolve_macro_progress(
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        remaining_calories=remaining_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        remaining_protein_g=remaining_protein_g,
    )
    target_cal = progress.get("target_calories")
    consumed_cal = progress.get("consumed_calories")
    target_protein = progress.get("target_protein_g")
    consumed_protein = progress.get("consumed_protein_g")

    hour = _safe_optional_float(current_hour)
    if hour is not None and hour < 18:
        return None

    if target_cal is None or consumed_cal is None or target_protein is None or consumed_protein is None:
        return None

    calorie_delta = abs(target_cal - consumed_cal)
    protein_ratio = consumed_protein / max(1.0, target_protein)

    if calorie_delta <= 150 and protein_ratio >= 0.9:
        return {
            "headline": "Solid day overall.",
            "supporting_text": "You stayed close to calories and kept protein strong.",
            "score_label": "On Track",
        }
    if consumed_cal > target_cal + 200:
        return {
            "headline": "Calories ran a bit high today.",
            "supporting_text": "Go lighter at the next meal and reset cleanly tomorrow.",
            "score_label": "Adjust Tomorrow",
        }
    if protein_ratio < 0.8:
        return {
            "headline": "Protein was still low today.",
            "supporting_text": "Aim for one more lean protein meal tomorrow.",
            "score_label": "Protein Focus",
        }

    return {
        "headline": "Decent day overall.",
        "supporting_text": "A little tighter portion control tomorrow can sharpen results.",
        "score_label": "Mostly On Track",
    }


def build_day_coach_payload(
    *,
    lunch_cards: Optional[List[Dict[str, Any]]] = None,
    target_calories: Any = None,
    consumed_calories: Any = None,
    remaining_calories: Any = None,
    target_protein_g: Any = None,
    consumed_protein_g: Any = None,
    remaining_protein_g: Any = None,
    goal: str = "",
    cut_mode: bool = False,
    current_hour: Any = None,
) -> Dict[str, Any]:
    cards = [row for row in (lunch_cards or []) if isinstance(row, dict)]
    best_card = next(
        (row for row in cards if str(row.get("card_type") or "").strip().lower() == "best_right_now"),
        cards[0] if cards else None,
    )

    day_summary = build_day_coach_summary(
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        remaining_calories=remaining_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        remaining_protein_g=remaining_protein_g,
        goal=goal,
        cut_mode=cut_mode,
    )

    payload: Dict[str, Any] = {
        "day_summary": day_summary,
        "coach_version": DAY_COACH_VERSION,
    }

    next_meal = build_next_meal_guidance(
        top_recommendation=best_card,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        goal=goal,
        cut_mode=cut_mode,
    )
    if next_meal:
        payload["next_meal_guidance"] = next_meal

    evening = build_evening_guidance(
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        current_hour=current_hour,
        cut_mode=cut_mode,
        goal=goal,
    )
    if evening:
        payload["evening_guidance"] = evening

    end_feedback = build_end_of_day_feedback(
        target_calories=target_calories,
        consumed_calories=consumed_calories,
        target_protein_g=target_protein_g,
        consumed_protein_g=consumed_protein_g,
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        current_hour=current_hour,
    )
    if end_feedback:
        payload["end_of_day_feedback"] = end_feedback

    return payload
