from __future__ import annotations

from typing import Any, Dict, Optional


COACH_MESSAGE_VERSION = "v1"


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


def _decision_token(today_fit: Dict[str, Any], place: Dict[str, Any]) -> str:
    token = str(today_fit.get("decision") or place.get("decision_today") or "").strip().upper()
    if token in {"YES", "MAYBE", "NO"}:
        return token

    fit = place.get("fit_for_today")
    if fit is True:
        return "YES"
    if fit is False:
        return "NO"
    return "MAYBE"


def _protein_values(top_menu_item: Dict[str, Any], place: Dict[str, Any]) -> int:
    return _safe_int(
        top_menu_item.get("estimated_protein_g"),
        _safe_int(place.get("estimated_protein_g"), 0),
    )


def _calorie_saved(reality_check: Dict[str, Any]) -> int:
    return max(0, _safe_int(reality_check.get("calories_saved"), 0))


def build_place_coach_message(
    place: Dict[str, Any],
    top_menu_item: Optional[Dict[str, Any]] = None,
    today_fit: Optional[Dict[str, Any]] = None,
    reality_check: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    place_payload = place if isinstance(place, dict) else {}
    menu_payload = top_menu_item if isinstance(top_menu_item, dict) else {}
    fit_payload = today_fit if isinstance(today_fit, dict) else {}
    reality_payload = reality_check if isinstance(reality_check, dict) else {}
    ctx = context if isinstance(context, dict) else {}

    decision = _decision_token(fit_payload, place_payload)
    calories_saved = _calorie_saved(reality_payload)
    protein_g = _protein_values(menu_payload, place_payload)

    cut_mode = bool(ctx.get("cut_mode") or place_payload.get("cut_mode_active"))
    goal = str(ctx.get("goal") or place_payload.get("personalization_goal") or "").strip().lower()
    remaining_protein_g = _safe_float(
        ctx.get("remaining_protein_g"),
        _safe_float(place_payload.get("remaining_protein_g"), 0.0),
    )

    headline = "Better choice nearby for your goal."
    supporting_text = "Pick lean protein and keep extras light."
    tone = "encouraging"

    if decision == "NO":
        headline = "Harder to fit today unless you keep it light."
        supporting_text = "Skip heavier extras and choose the leanest order if you still eat here."
        tone = "warning"
    elif decision == "MAYBE":
        headline = "Possible today if you keep the order light."
        supporting_text = "Choose lean protein and skip high-calorie sides or sauces."
        tone = "caution"
    else:
        if calories_saved >= 300:
            headline = f"Smarter swap — you save {calories_saved} kcal here."
            supporting_text = "Much easier to stay on target than the usual order."
        elif (goal == "fat_loss" or cut_mode) and protein_g >= 35:
            headline = "Strong protein choice for your cut."
            supporting_text = "High protein and easier calorie control for today."
        elif remaining_protein_g >= 35 and protein_g >= 28:
            headline = "You’re still short on protein today — this helps."
            supporting_text = "A practical way to close your protein gap without overdoing calories."
        else:
            headline = "Best fit for your remaining calories."
            supporting_text = "Balanced choice that stays macro-friendly right now."

    # Blend in an existing precise decision reason when useful.
    decision_reason = str(fit_payload.get("decision_reason") or place_payload.get("decision_reason") or "").strip()
    if decision_reason:
        if decision == "NO":
            supporting_text = decision_reason
        elif decision == "MAYBE" and "swap" not in supporting_text.lower():
            supporting_text = decision_reason

    health_score_100 = _safe_float(place_payload.get("health_score_100"), _safe_float(place_payload.get("health_score"), 0.0))
    if health_score_100 <= 10:
        health_score_100 *= 10.0

    confidence = 0.58
    if decision in {"YES", "NO"}:
        confidence += 0.08
    if protein_g > 0:
        confidence += 0.08
    if calories_saved > 0:
        confidence += 0.08
    if health_score_100 >= 75:
        confidence += 0.07
    if not str(menu_payload.get("item_name") or place_payload.get("best_order") or "").strip():
        confidence -= 0.07

    return {
        "headline": headline,
        "supporting_text": supporting_text,
        "tone": tone,
        "confidence": round(_clamp(confidence, 0.45, 0.92), 2),
        "message_version": COACH_MESSAGE_VERSION,
    }
