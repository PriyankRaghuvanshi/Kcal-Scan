from __future__ import annotations

import hashlib
from typing import Any, Dict, Optional, Sequence

from llm_coach_phrasing import maybe_rephrase_coach_message


COACH_MESSAGE_VERSION = "v2"


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


def _menu_source_token(top_menu_item: Dict[str, Any], place: Dict[str, Any]) -> str:
    token = str(
        top_menu_item.get("menu_item_source")
        or place.get("menu_item_source")
        or place.get("menu_items_source")
        or "heuristic"
    ).strip().lower()
    if token in {
        "real_menu",
        "menu_intelligence_store",
        "structured_menu",
        "scraped_menu",
        "user_scan",
        "website_menu",
        "website_text",
        "review_text",
        "ocr_menu",
    }:
        return "real_menu"
    if token in {"llm_inferred", "llm"}:
        return "llm_inferred"
    return "heuristic"


def _variant_index(*parts: Any, modulo: int) -> int:
    seed = "|".join(str(part or "").strip().lower() for part in parts)
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % max(1, int(modulo or 1))


def _pick_variant(options: Sequence[Sequence[str]], *parts: Any) -> tuple[str, str]:
    variants = [tuple(opt) for opt in options if isinstance(opt, (list, tuple)) and len(opt) >= 2]
    if not variants:
        return ("Better choice nearby for your goal.", "Pick lean protein and keep extras light.")
    idx = _variant_index(*parts, modulo=len(variants))
    chosen = variants[idx]
    return str(chosen[0]), str(chosen[1])


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
    menu_source = _menu_source_token(menu_payload, place_payload)
    menu_confidence_raw = menu_payload.get("menu_item_confidence")
    if menu_confidence_raw is None:
        menu_confidence_raw = place_payload.get("menu_item_confidence")
    menu_confidence = None if menu_confidence_raw is None else _clamp(_safe_float(menu_confidence_raw, 0.0), 0.0, 1.0)

    cut_mode = bool(ctx.get("cut_mode") or place_payload.get("cut_mode_active"))
    goal = str(ctx.get("goal") or place_payload.get("personalization_goal") or "").strip().lower()
    remaining_protein_g = _safe_float(
        ctx.get("remaining_protein_g"),
        _safe_float(place_payload.get("remaining_protein_g"), 0.0),
    )

    variant_parts = (
        place_payload.get("place_id") or place_payload.get("name") or place_payload.get("place_name") or "unknown_place",
        menu_payload.get("item_name") or place_payload.get("best_order") or "unknown_item",
        decision,
        goal,
        str(cut_mode).lower(),
    )
    headline = "Better choice nearby for your goal."
    supporting_text = "Pick lean protein and keep extras light."
    tone = "encouraging"

    if decision == "NO":
        headline, supporting_text = _pick_variant(
            [
                ("Harder to fit today unless you keep it light.", "Skip heavier extras and choose the leanest order if you still eat here."),
                ("This one runs heavy today.", "If you still go for it, keep the order tight and cut the extras."),
                ("Tougher fit for today’s target.", "Best move here is the leanest protein and no calorie-dense add-ons."),
            ],
            *variant_parts,
        )
        tone = "warning"
    elif decision == "MAYBE":
        headline, supporting_text = _pick_variant(
            [
                ("Possible today if you keep the order light.", "Choose lean protein and skip high-calorie sides or sauces."),
                ("Could work if you keep it simple.", "Go lighter on sauces, sides, and extras to keep this manageable."),
                ("Borderline fit, but still workable.", "A cleaner order keeps this inside range much more easily."),
            ],
            *variant_parts,
        )
        tone = "caution"
    else:
        if calories_saved >= 300:
            headline, supporting_text = _pick_variant(
                [
                    (f"Smarter swap — you save {calories_saved} kcal here.", "Much easier to stay on target than the usual order."),
                    (f"Big calorie win here — about {calories_saved} kcal saved.", "This swap gives you more room for the rest of the day."),
                    (f"Cleaner order, roughly {calories_saved} kcal lighter.", "A strong trade-up if you want the easier fat-loss option."),
                ],
                *variant_parts,
                calories_saved,
            )
        elif (goal == "fat_loss" or cut_mode) and protein_g >= 35:
            headline, supporting_text = _pick_variant(
                [
                    ("Strong protein choice for your cut.", "High protein and easier calorie control for today."),
                    ("Cut-friendly pick with solid protein.", "This gives you better fullness without pushing calories too hard."),
                    ("Lean enough to help your cut today.", "You get useful protein here without making the day harder to fit."),
                ],
                *variant_parts,
                protein_g,
            )
        elif remaining_protein_g >= 35 and protein_g >= 28:
            headline, supporting_text = _pick_variant(
                [
                    ("You’re still short on protein today — this helps.", "A practical way to close your protein gap without overdoing calories."),
                    ("Protein catch-up option right now.", "This moves the day forward without forcing a heavy meal."),
                    ("Useful protein top-up for today.", "A smart way to chip away at the gap while keeping the order reasonable."),
                ],
                *variant_parts,
                remaining_protein_g,
            )
        else:
            headline, supporting_text = _pick_variant(
                [
                    ("Best fit for your remaining calories.", "Balanced choice that stays macro-friendly right now."),
                    ("One of the easier nearby fits right now.", "A sensible option if you want decent macros without overthinking it."),
                    ("Good fit for the rest of your day.", "Keeps the next meal practical and easier to absorb into your targets."),
                ],
                *variant_parts,
                protein_g,
            )

    # Blend in an existing precise decision reason when useful.
    decision_reason = str(fit_payload.get("decision_reason") or place_payload.get("decision_reason") or "").strip()
    if decision_reason:
        if decision == "NO":
            supporting_text = decision_reason
        elif decision == "MAYBE" and "swap" not in supporting_text.lower():
            supporting_text = decision_reason

    # Avoid sounding certain when recommendation source/confidence is weak.
    if menu_source != "real_menu" and menu_confidence is not None and menu_confidence < 0.55:
        if decision == "YES":
            headline = "Likely good fit if you keep choices simple."
            supporting_text = "Menu details look limited, so choose lighter and less oily options."
            tone = "caution"
        elif decision == "MAYBE":
            headline = "Could work today with a lighter order."
            supporting_text = "Menu details are limited, so keep portions and extras controlled."
            tone = "caution"
        else:
            headline = "Hard to confirm fit from this menu."
            supporting_text = "If you still eat here, keep it light and avoid heavier extras."
            tone = "warning"

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
    if menu_source != "real_menu" and menu_confidence is not None:
        confidence -= 0.05
    if menu_confidence is not None:
        confidence += (menu_confidence - 0.5) * 0.18

    phrased = maybe_rephrase_coach_message(
        headline=headline,
        supporting_text=supporting_text,
        context={
            "tone": tone,
            "goal": goal,
            "decision": decision,
            "cut_mode": cut_mode,
            "menu_item_source": menu_source,
            "menu_item_confidence": "" if menu_confidence is None else menu_confidence,
        },
    )

    return {
        "headline": str(phrased.get("headline") or headline),
        "supporting_text": str(phrased.get("supporting_text") or supporting_text),
        "tone": tone,
        "confidence": round(_clamp(confidence, 0.45, 0.92), 2),
        "message_version": COACH_MESSAGE_VERSION,
        "phrasing_method": str(phrased.get("phrasing_method") or "deterministic"),
        "phrasing_version": str(phrased.get("phrasing_version") or "v1"),
    }
