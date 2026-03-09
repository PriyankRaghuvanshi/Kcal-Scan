from __future__ import annotations

import os
import re
from typing import Any, Dict


SCORE_MODIFIER_VERSION = "v1_base_plus_modifiers"

PHASE_1 = "phase_1"
PHASE_2 = "phase_2"
PHASE_3 = "phase_3"

_VALID_PHASES = {PHASE_1, PHASE_2, PHASE_3}

PHASE_SCALE: Dict[str, float] = {
    PHASE_1: 0.35,  # mostly observational/light influence
    PHASE_2: 0.65,  # moderate influence
    PHASE_3: 1.00,  # full influence
}

PHASE_ABS_CAP: Dict[str, float] = {
    PHASE_1: 3.5,
    PHASE_2: 6.0,
    PHASE_3: 8.5,
}

# Conservative defaults: base score remains dominant.
MODIFIER_MAX_IMPACT: Dict[str, float] = {
    "upf_penalty": 6.0,
    "bioavailability_bonus": 2.4,
    "micronutrient_bonus": 2.2,
    "price_fit_modifier": 1.8,
    "personal_response_history_modifier": 2.2,
}

_REAL_MENU_SOURCES = {"real_menu", "user_scan"}

_POSITIVE_MICRO_TOKENS = (
    "salad",
    "greens",
    "vegetable",
    "veggie",
    "lentil",
    "dal",
    "bean",
    "chickpea",
    "brown rice",
    "quinoa",
    "wholegrain",
    "whole grain",
    "fruit",
    "idli",
    "dosa",
    "sambar",
)

_UPF_RISK_TOKENS = (
    "loaded",
    "double",
    "triple",
    "combo",
    "bucket",
    "family meal",
    "fried",
    "crispy",
    "fries",
    "shake",
    "soda",
    "dessert",
    "pastry",
    "cheesy",
    "processed",
)

_NORM_RE = re.compile(r"[^a-z0-9\s]")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _norm_text(value: Any) -> str:
    raw = str(value or "").strip().lower()
    if not raw:
        return ""
    return " ".join(_NORM_RE.sub(" ", raw).split())


def _normalize_source(value: Any) -> str:
    token = _norm_text(value)
    if token in {"user scan", "userscan"}:
        return "user_scan"
    if token in {"real menu", "real_menu", "website menu", "website text", "structured menu", "menu intelligence store", "scraped menu", "review text", "ocr menu"}:
        return "real_menu"
    if token in {"llm", "llm inferred", "llm_inferred"}:
        return "llm_inferred"
    if token == "user_scan":
        return "user_scan"
    return "heuristic"


def _phase_token(context: Dict[str, Any]) -> str:
    env_phase = str(os.getenv("HEALTHY_NEARBY_SCORE_MODIFIER_PHASE", PHASE_1) or PHASE_1).strip().lower()
    context_phase = str(context.get("modifier_rollout_phase") or "").strip().lower()
    phase = context_phase or env_phase
    if phase not in _VALID_PHASES:
        return PHASE_1
    return phase


def _modifier_inputs(payload: Dict[str, Any]) -> Dict[str, Any]:
    top = payload.get("top_menu_item") if isinstance(payload.get("top_menu_item"), dict) else {}
    breakdown = top.get("item_score_breakdown") if isinstance(top.get("item_score_breakdown"), dict) else {}

    source = _normalize_source(
        top.get("menu_item_source")
        or payload.get("menu_item_source")
        or payload.get("menu_source_resolved")
        or payload.get("menu_items_source_resolved")
        or payload.get("menu_source")
        or payload.get("menu_items_source")
    )
    item_name = str(top.get("item_name") or payload.get("recommended_order") or payload.get("best_order") or "").strip()
    item_text = _norm_text(item_name)

    calories = max(
        0.0,
        _safe_float(top.get("estimated_calories"), _safe_float(payload.get("estimated_calories"), 0.0)),
    )
    protein = max(
        0.0,
        _safe_float(top.get("estimated_protein_g"), _safe_float(payload.get("estimated_protein_g"), 0.0)),
    )
    conf = _clamp(
        _safe_float(
            top.get("menu_item_confidence"),
            _safe_float(payload.get("menu_item_confidence"), _safe_float(payload.get("menu_confidence"), 0.0)),
        ),
        0.0,
        1.0,
    )
    order_type = str(top.get("order_type") or payload.get("order_type") or "").strip().lower()

    return {
        "top": top,
        "breakdown": breakdown,
        "source": source,
        "item_text": item_text,
        "calories": calories,
        "protein": protein,
        "confidence": conf,
        "order_type": order_type,
    }


def _upf_signal(inputs: Dict[str, Any]) -> float:
    breakdown = inputs["breakdown"]
    item_text = inputs["item_text"]

    processing = _safe_float(breakdown.get("processing_penalty"), 0.0)
    fried = _safe_float(breakdown.get("fried_penalty"), 0.0)
    sugar = _safe_float(breakdown.get("sugar_penalty"), 0.0)

    if processing > 0 or fried > 0 or sugar > 0:
        signal = ((processing * 0.45) + (fried * 0.35) + (sugar * 0.20)) / 100.0
        return _clamp(signal, 0.0, 1.0)

    token_hits = sum(1 for token in _UPF_RISK_TOKENS if token in item_text)
    signal = token_hits * 0.12
    if bool(inputs["top"].get("cut_friendly")):
        signal -= 0.08
    return _clamp(signal, 0.0, 1.0)


def _bioavailability_signal(inputs: Dict[str, Any]) -> float:
    protein = float(inputs["protein"])
    calories = max(1.0, float(inputs["calories"]))
    source = str(inputs["source"])
    order_type = str(inputs["order_type"])
    upf = _upf_signal(inputs)

    signal = 0.0
    if protein >= 35:
        signal += 0.45
    elif protein >= 25:
        signal += 0.28

    density = protein / calories
    if density >= 0.060:
        signal += 0.25
    elif density >= 0.045:
        signal += 0.14

    if source in _REAL_MENU_SOURCES:
        signal += 0.14
    if order_type == "exact":
        signal += 0.12
    elif order_type == "likely":
        signal += 0.06

    if upf >= 0.65:
        signal -= 0.12

    return _clamp(signal, 0.0, 1.0)


def _micronutrient_signal(inputs: Dict[str, Any]) -> float:
    item_text = str(inputs["item_text"])
    source = str(inputs["source"])
    conf = float(inputs["confidence"])
    top = inputs["top"]

    token_hits = sum(1 for token in _POSITIVE_MICRO_TOKENS if token in item_text)
    signal = min(0.78, token_hits * 0.14)

    health_signals = top.get("health_signals") if isinstance(top.get("health_signals"), list) else []
    if "high_fiber" in health_signals:
        signal += 0.16
    if "vegetable_forward" in health_signals:
        signal += 0.10
    if "deep_fried" in health_signals:
        signal -= 0.10

    if conf < 0.45:
        signal *= 0.60
    elif conf < 0.60:
        signal *= 0.82
    if source == "heuristic":
        signal *= 0.74

    return _clamp(signal, 0.0, 1.0)


def _price_fit_signal(payload: Dict[str, Any], context: Dict[str, Any]) -> float:
    price_level = payload.get("price_level")
    if price_level is None:
        price_level = payload.get("price_tier")
    if price_level is None:
        price_level = payload.get("price_fit_score")
        if price_level is not None:
            return _clamp(_safe_float(price_level, 0.0), -1.0, 1.0)
        return 0.0

    level = _safe_float(price_level, 0.0)
    if level <= 0:
        return 0.10
    if level <= 2:
        return 0.40
    if level >= 4:
        return -0.35
    return 0.0


def _personal_history_signal(payload: Dict[str, Any], context: Dict[str, Any]) -> float:
    raw = context.get("personal_response_history_score")
    if raw is None:
        raw = payload.get("personal_response_history_score")
    if raw is None:
        return 0.0

    signal = _clamp(_safe_float(raw, 0.0), -1.0, 1.0)
    events = context.get("personal_history_events")
    if events is None:
        events = payload.get("personal_history_events")
    n = _safe_float(events, 0.0)
    if n < 5:
        signal *= 0.35
    elif n < 12:
        signal *= 0.65
    return _clamp(signal, -1.0, 1.0)


def apply_score_modifiers(
    *,
    base_score: Any,
    payload: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    row = payload if isinstance(payload, dict) else {}
    ctx = context if isinstance(context, dict) else {}
    base = _clamp(_safe_float(base_score, 0.0), 0.0, 100.0)

    phase = _phase_token(ctx)
    phase_scale = float(PHASE_SCALE.get(phase, PHASE_SCALE[PHASE_1]))
    max_abs = float(PHASE_ABS_CAP.get(phase, PHASE_ABS_CAP[PHASE_1]))

    inputs = _modifier_inputs(row)

    upf_penalty_raw = -_upf_signal(inputs) * MODIFIER_MAX_IMPACT["upf_penalty"]
    bio_bonus_raw = _bioavailability_signal(inputs) * MODIFIER_MAX_IMPACT["bioavailability_bonus"]
    micro_bonus_raw = _micronutrient_signal(inputs) * MODIFIER_MAX_IMPACT["micronutrient_bonus"]
    price_mod_raw = _price_fit_signal(row, ctx) * MODIFIER_MAX_IMPACT["price_fit_modifier"]
    personal_mod_raw = _personal_history_signal(row, ctx) * MODIFIER_MAX_IMPACT["personal_response_history_modifier"]

    raw_total = upf_penalty_raw + bio_bonus_raw + micro_bonus_raw + price_mod_raw + personal_mod_raw
    scaled_total = _clamp(raw_total * phase_scale, -max_abs, max_abs)
    final_score = _clamp(base + scaled_total, 0.0, 100.0)
    factor = final_score / max(1e-6, base) if base > 0 else 1.0

    return {
        "base_score": round(base, 2),
        "modifier_score_raw": round(raw_total, 2),
        "modifier_score": round(scaled_total, 2),
        "final_score": round(final_score, 2),
        "score_adjustment_factor": round(_clamp(factor, 0.85, 1.15), 4),
        "modifier_rollout_phase": phase,
        "modifier_version": SCORE_MODIFIER_VERSION,
        "modifier_breakdown": {
            "upf_penalty": {
                "raw": round(upf_penalty_raw, 2),
                "applied": round(upf_penalty_raw * phase_scale, 2),
            },
            "bioavailability_bonus": {
                "raw": round(bio_bonus_raw, 2),
                "applied": round(bio_bonus_raw * phase_scale, 2),
            },
            "micronutrient_bonus": {
                "raw": round(micro_bonus_raw, 2),
                "applied": round(micro_bonus_raw * phase_scale, 2),
            },
            "price_fit_modifier": {
                "raw": round(price_mod_raw, 2),
                "applied": round(price_mod_raw * phase_scale, 2),
            },
            "personal_response_history_modifier": {
                "raw": round(personal_mod_raw, 2),
                "applied": round(personal_mod_raw * phase_scale, 2),
            },
            "total": {
                "raw": round(raw_total, 2),
                "applied": round(scaled_total, 2),
                "phase_scale": round(phase_scale, 3),
                "phase_abs_cap": round(max_abs, 2),
            },
        },
    }

