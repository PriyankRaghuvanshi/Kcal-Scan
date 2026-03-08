from __future__ import annotations

from typing import Any, Dict


DECISION_ENGINE_VERSION = "v1"


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_optional_float(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except Exception:
        return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _meal_protein_target(remaining_protein_g: float) -> float:
    # Practical per-meal target so this stays useful even with large daily protein gaps.
    return float(_clamp(max(20.0, remaining_protein_g * 0.45), 20.0, 35.0))


def _skipped_decision(reason: str = "") -> Dict[str, Any]:
    return {
        "decision_today": None,
        "decision_reason": str(reason or ""),
        "fits_remaining_calories": None,
        "fits_remaining_protein": None,
        "decision_confidence": None,
        "decision_version": DECISION_ENGINE_VERSION,
    }


def evaluate_place_for_today(
    *,
    estimated_calories: Any,
    estimated_protein_g: Any,
    remaining_calories: Any = None,
    remaining_protein_g: Any = None,
    health_score: Any = None,
) -> Dict[str, Any]:
    """
    Decide whether this venue fits today's remaining macro budget.
    Returns YES / MAYBE / NO with short UI-ready reasoning.
    """
    remaining_cal = _safe_optional_float(remaining_calories)
    remaining_protein = _safe_optional_float(remaining_protein_g)

    # No daily context provided: keep response backward compatible and skip safely.
    if remaining_cal is None and remaining_protein is None:
        return _skipped_decision()

    if remaining_cal is None:
        return _skipped_decision("Set remaining calories to enable today's decision.")

    remaining_cal = max(0.0, float(remaining_cal))
    est_cal = max(0.0, _safe_float(estimated_calories, 520.0))
    est_protein = max(0.0, _safe_float(estimated_protein_g, 32.0))
    health_score_10pt = _clamp(_safe_float(health_score, 5.0), 1.0, 10.0)

    protein_context_available = remaining_protein is not None
    if protein_context_available:
        remaining_protein = max(0.0, float(remaining_protein))

    fits_calories = est_cal <= remaining_cal
    near_calorie_limit = est_cal <= (remaining_cal * 1.12)

    fits_protein: bool | None = None
    protein_coverage = 1.0
    if protein_context_available:
        if remaining_protein <= 0.0:
            fits_protein = True
            protein_coverage = 1.0
        else:
            protein_target = _meal_protein_target(remaining_protein)
            fits_protein = est_protein >= protein_target
            protein_coverage = _clamp(est_protein / max(1.0, protein_target), 0.0, 1.0)

    if remaining_cal <= 0.0:
        decision = "NO"
        reason = "No calorie budget left for today."
    elif not protein_context_available:
        if fits_calories:
            decision = "YES"
            reason = "Fits your remaining calories today."
        elif near_calorie_limit:
            decision = "MAYBE"
            reason = "Close to your remaining calorie limit."
        else:
            decision = "NO"
            reason = "Likely over your remaining calorie budget."
    else:
        moderate_protein = bool(
            est_protein >= max(18.0, _meal_protein_target(float(remaining_protein or 0.0)) * 0.7)
        )
        if fits_calories and bool(fits_protein):
            decision = "YES"
            reason = "Fits remaining calories and gives strong protein."
        elif (fits_calories and moderate_protein) or (near_calorie_limit and bool(fits_protein)):
            decision = "MAYBE"
            reason = "Mostly fits today, but keep portions and sides controlled."
        elif fits_calories:
            decision = "MAYBE"
            reason = "Fits calories, but protein is lower than your remaining target."
        elif near_calorie_limit:
            decision = "MAYBE"
            reason = "Slightly above calories; use swaps to stay on track."
        else:
            decision = "NO"
            reason = "Most options here are too calorie-dense for your budget."

    if decision == "YES":
        headroom = 0.0
        if remaining_cal > 0.0:
            headroom = _clamp((remaining_cal - est_cal) / remaining_cal, 0.0, 1.0)
        confidence = 0.66 + (headroom * 0.16) + (protein_coverage * 0.12) + ((health_score_10pt / 10.0) * 0.06)
    elif decision == "MAYBE":
        closeness = 0.0
        if remaining_cal > 0.0:
            closeness = 1.0 - _clamp(abs(est_cal - remaining_cal) / remaining_cal, 0.0, 1.0)
        confidence = 0.50 + (closeness * 0.18) + (protein_coverage * 0.10)
    else:
        if remaining_cal <= 0.0:
            confidence = 0.95
        else:
            overage = _clamp((est_cal - remaining_cal) / max(1.0, remaining_cal), 0.0, 2.0)
            confidence = 0.66 + min(0.24, overage * 0.28)

    return {
        "decision_today": decision,
        "decision_reason": reason,
        "fits_remaining_calories": bool(fits_calories),
        "fits_remaining_protein": fits_protein,
        "decision_confidence": round(_clamp(confidence, 0.35, 0.96), 2),
        "decision_version": DECISION_ENGINE_VERSION,
    }
