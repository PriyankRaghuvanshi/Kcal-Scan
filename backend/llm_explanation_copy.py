from __future__ import annotations

import json
import os
from typing import Any, Dict, Tuple

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - may be unavailable in slim test envs.
    genai = None  # type: ignore[assignment]


LLM_EXPLANATION_COPY_VERSION = "v1"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_MAX_WHY_WORDS = 16
_MAX_SHORT_WORDS = 12
_MAX_WHY_CHARS = 120
_MAX_SHORT_CHARS = 90
_BANNED_PHRASES = (
    "wellness journey",
    "holistic",
    "algorithm",
    "lifestyle",
    "optimal",
    "revolutionary",
    "macro-optimized",
)
_OVERSOLD_PHRASES = ("perfect", "ideal", "guaranteed", "best possible", "always")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return _normalized(raw).lower() in _TRUE_VALUES


def _llm_available() -> bool:
    return bool(genai is not None) and bool(str(os.getenv("GEMINI_API_KEY", "") or "").strip())


def _model_name() -> str:
    return (
        str(os.getenv("EXPLANATION_COPY_LLM_MODEL", "") or "").strip()
        or str(os.getenv("COACH_LLM_MODEL", "") or "").strip()
        or str(os.getenv("SCAN_LLM_MODEL", "") or "").strip()
        or "gemini-2.5-flash"
    )


def _timeout_sec() -> float:
    try:
        value = float(str(os.getenv("EXPLANATION_COPY_TIMEOUT_SEC", "3.5") or "3.5").strip())
    except Exception:
        value = 3.5
    return max(2.0, min(6.0, value))


def _word_count(text: str) -> int:
    return len([part for part in _normalized(text).split(" ") if part])


def _strip_fences(text: str) -> str:
    payload = str(text or "").strip()
    if payload.startswith("```json"):
        payload = payload[len("```json") :].strip()
    if payload.startswith("```"):
        payload = payload[len("```") :].strip()
    if payload.endswith("```"):
        payload = payload[:-3].strip()
    return payload


def _extract_json(text: str) -> Dict[str, Any] | None:
    payload = _strip_fences(text)
    if not payload:
        return None
    try:
        obj = json.loads(payload)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(payload[start : end + 1])
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def _source_token(source: Any) -> str:
    token = _normalized(source).lower().replace("-", "_")
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


def _fit_token(today_fit: Any) -> str:
    raw = _normalized(today_fit).upper()
    if raw in {"YES", "MAYBE", "NO"}:
        return raw
    if isinstance(today_fit, bool):
        return "YES" if today_fit else "NO"
    return ""


def _effective_confidence(confidence: Any, menu_item_confidence: Any) -> float:
    conf = _safe_float(confidence, 0.0)
    menu_conf = _safe_float(menu_item_confidence, 0.0)
    if conf > 0 and menu_conf > 0:
        merged = (conf * 0.55) + (menu_conf * 0.45)
    elif conf > 0:
        merged = conf
    elif menu_conf > 0:
        merged = menu_conf
    else:
        merged = 0.48
    return round(_clamp(merged, 0.2, 0.95), 2)


def _cuisine_bucket(cuisine: str, place_name: str) -> str:
    text = f"{_normalized(cuisine)} {_normalized(place_name)}".lower()
    if any(token in text for token in ("south indian", "idli", "dosa", "udupi", "tiffin", "temple", "canteen", "sambar")):
        return "south_indian"
    if any(token in text for token in ("indian", "dal", "paneer", "tandoori", "biryani", "thali", "masala")):
        return "indian"
    if any(token in text for token in ("cafe", "coffee", "bakery", "brunch")):
        return "cafe"
    if any(token in text for token in ("burger", "fast food", "fast_food", "fried chicken", "kfc", "mcdonald")):
        return "fast_food"
    if "pizza" in text:
        return "pizza"
    return "generic"


def _looks_generic_westernized(text: str) -> bool:
    lower = _normalized(text).lower()
    return any(token in lower for token in ("protein bowl", "lean wrap-style", "grilled wrap", "macro-optimized"))


def _deterministic_context_copy(
    *,
    bucket: str,
    source: str,
    confidence: float,
    fit_token: str,
) -> Tuple[str, str]:
    low_conf = confidence < 0.55 or source == "heuristic"

    if bucket == "south_indian":
        if low_conf:
            return (
                "Likely easier to fit with simpler South Indian options here.",
                "Prefer less oily, less fried tiffin-style picks.",
            )
        return (
            "A simpler South Indian choice is easier to fit today.",
            "Choose lighter dosa or idli-style options over richer picks.",
        )

    if bucket == "indian":
        if low_conf:
            return (
                "Likely better fit with simpler Indian options here.",
                "Choose less oily dishes and keep richer sides controlled.",
            )
        return (
            "This works better when you keep Indian choices lighter.",
            "Prefer grilled or simpler dal-based options over richer curries.",
        )

    if bucket == "cafe":
        return (
            "Can work today if you keep cafe choices simple.",
            "Skip pastries and sweet drinks for better calorie control.",
        )

    if bucket == "fast_food":
        return (
            "A leaner swap here usually fits calories better.",
            "Skip fries and sugary drinks if you are cutting.",
        )

    if bucket == "pizza":
        return (
            "A lighter pizza choice can fit your calories more easily.",
            "Keep portions smaller and avoid heavy extras.",
        )

    if low_conf:
        return (
            "Suggested lighter option; menu details are still limited.",
            "Look for simpler, less fried choices here.",
        )

    if fit_token == "NO":
        return (
            "Harder to fit today unless you keep this order lighter.",
            "Use strict swaps to stay within your calories.",
        )
    if fit_token == "MAYBE":
        return (
            "This can work today with careful swaps.",
            "Keep portions and richer extras controlled.",
        )
    return (
        "Likely better fit for your current calorie target.",
        "A cleaner choice for steadier protein and calories.",
    )


def _valid_copy(why_this_works: str, short_reason: str) -> bool:
    if not why_this_works or not short_reason:
        return False
    if _word_count(why_this_works) > _MAX_WHY_WORDS:
        return False
    if _word_count(short_reason) > _MAX_SHORT_WORDS:
        return False
    if len(why_this_works) > _MAX_WHY_CHARS:
        return False
    if len(short_reason) > _MAX_SHORT_CHARS:
        return False

    lower_blob = f"{why_this_works} {short_reason}".lower()
    if any(token in lower_blob for token in _BANNED_PHRASES):
        return False
    return True


def _trust_guard(
    *,
    why_this_works: str,
    short_reason: str,
    recommended_order: str,
    bucket: str,
    source: str,
    confidence: float,
) -> Tuple[bool, str]:
    merged = f"{why_this_works} {short_reason}".lower()
    if any(token in merged for token in _OVERSOLD_PHRASES):
        return False, "overconfident_copy"

    if source != "real_menu" and confidence < 0.55:
        order = _normalized(recommended_order).lower()
        if order and len(order) >= 6 and order in merged:
            return False, "over_specific_low_confidence"
        if bucket in {"south_indian", "indian"} and _looks_generic_westernized(merged):
            return False, "cuisine_mismatch_low_confidence"
    return True, ""


def _build_prompt(
    *,
    place_name: str,
    cuisine: str,
    recommended_order: str,
    estimated_calories: Any,
    estimated_protein_g: Any,
    typical_order_calories: Any,
    goal: str,
    confidence: Any,
    recommendation_source: str,
    menu_item_confidence: Any,
    today_fit: str,
    has_reality_check: bool,
    base_why_this_works: str,
    base_short_reason: str,
) -> str:
    cal = int(max(0, round(_safe_float(estimated_calories, 0.0))))
    protein = int(max(0, round(_safe_float(estimated_protein_g, 0.0))))
    typical_cal = int(max(0, round(_safe_float(typical_order_calories, 0.0))))
    conf = max(0.0, min(1.0, _safe_float(confidence, 0.0)))
    menu_conf = max(0.0, min(1.0, _safe_float(menu_item_confidence, 0.0)))

    return (
        "You rewrite short nutrition recommendation copy for a mobile app.\n"
        "Return ONLY JSON with keys: why_this_works, short_reason, copy_confidence.\n"
        "Rules:\n"
        f"- why_this_works max {_MAX_WHY_WORDS} words.\n"
        f"- short_reason max {_MAX_SHORT_WORDS} words.\n"
        "- One sentence per field.\n"
        "- Keep meaning aligned with base text.\n"
        "- Be restaurant/cuisine aware.\n"
        "- No hype, no fluff, no jargon.\n"
        "- If source is heuristic or confidence is low, use softer wording.\n"
        "- Do NOT invent exact dish names when confidence is low.\n"
        "- For Indian/South Indian/temple/canteen contexts, avoid westernized generic fitness-food language.\n"
        "- copy_confidence must be in [0,1].\n"
        f"place_name: {place_name or 'Nearby place'}\n"
        f"cuisine_or_type: {cuisine or 'restaurant'}\n"
        f"recommended_order: {recommended_order or 'smart order'}\n"
        f"estimated_calories: {cal}\n"
        f"estimated_protein_g: {protein}\n"
        f"typical_order_calories: {typical_cal}\n"
        f"user_goal: {goal or 'balanced eating'}\n"
        f"recommendation_confidence: {round(conf, 2)}\n"
        f"menu_item_confidence: {round(menu_conf, 2)}\n"
        f"recommendation_source: {recommendation_source}\n"
        f"today_fit: {today_fit or 'UNKNOWN'}\n"
        f"reality_check_present: {str(bool(has_reality_check)).lower()}\n"
        f"base_why_this_works: {base_why_this_works}\n"
        f"base_short_reason: {base_short_reason}\n"
    )


def _invoke_llm(prompt: str) -> str:
    if not _llm_available():
        raise RuntimeError("llm_unavailable")

    api_key = str(os.getenv("GEMINI_API_KEY", "") or "").strip()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(_model_name())
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.2, "response_mime_type": "application/json"},
        request_options={"timeout": float(_timeout_sec())},
    )
    return str(getattr(response, "text", "") or "").strip()


def maybe_rewrite_explanation_copy(
    *,
    place_name: Any = "",
    cuisine: Any = "",
    recommended_order: Any = "",
    estimated_calories: Any = None,
    estimated_protein_g: Any = None,
    typical_order_calories: Any = None,
    goal: Any = "",
    confidence: Any = None,
    recommendation_source: Any = "heuristic",
    menu_item_confidence: Any = None,
    today_fit: Any = None,
    has_reality_check: Any = None,
    base_why_this_works: Any = "",
    base_short_reason: Any = "",
) -> Dict[str, Any]:
    source = _source_token(recommendation_source)
    fit = _fit_token(today_fit)
    merged_conf = _effective_confidence(confidence, menu_item_confidence)
    bucket = _cuisine_bucket(str(cuisine or ""), str(place_name or ""))

    fallback_why, fallback_short = _deterministic_context_copy(
        bucket=bucket,
        source=source,
        confidence=merged_conf,
        fit_token=fit,
    )

    why = _normalized(base_why_this_works) or _normalized(base_short_reason) or fallback_why
    short = _normalized(base_short_reason) or _normalized(base_why_this_works) or fallback_short

    # Harden deterministic copy for sparse/cuisine-specific contexts.
    if source != "real_menu" and merged_conf < 0.55:
        why = fallback_why
        short = fallback_short
    elif bucket in {"south_indian", "indian"} and (_looks_generic_westernized(why) or _looks_generic_westernized(short)):
        why = fallback_why
        short = fallback_short

    out = {
        "why_this_works": why,
        "short_reason": short,
        "copy_method": "deterministic",
        "copy_confidence": round(_clamp((merged_conf * 0.82) + 0.1, 0.35, 0.9), 2),
        "copy_version": LLM_EXPLANATION_COPY_VERSION,
        "copy_attempted": False,
        "copy_fallback_reason": "",
    }

    if not _env_bool("ENABLE_LLM_EXPLANATION_COPY", default=False):
        return out

    if not _llm_available():
        out["copy_attempted"] = True
        out["copy_fallback_reason"] = "llm_unavailable"
        return out

    out["copy_attempted"] = True
    try:
        prompt = _build_prompt(
            place_name=str(place_name or "").strip(),
            cuisine=str(cuisine or "").strip(),
            recommended_order=str(recommended_order or "").strip(),
            estimated_calories=estimated_calories,
            estimated_protein_g=estimated_protein_g,
            typical_order_calories=typical_order_calories,
            goal=str(goal or "").strip(),
            confidence=confidence,
            recommendation_source=source,
            menu_item_confidence=menu_item_confidence,
            today_fit=fit,
            has_reality_check=bool(has_reality_check),
            base_why_this_works=why,
            base_short_reason=short,
        )
        raw = _invoke_llm(prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            out["copy_fallback_reason"] = "invalid_llm_json"
            return out

        llm_why = _normalized(parsed.get("why_this_works"))
        llm_short = _normalized(parsed.get("short_reason"))
        if not _valid_copy(llm_why, llm_short):
            out["copy_fallback_reason"] = "output_too_long_or_invalid"
            return out

        trust_ok, trust_reason = _trust_guard(
            why_this_works=llm_why,
            short_reason=llm_short,
            recommended_order=str(recommended_order or ""),
            bucket=bucket,
            source=source,
            confidence=merged_conf,
        )
        if not trust_ok:
            out["copy_fallback_reason"] = trust_reason
            return out

        out["why_this_works"] = llm_why
        out["short_reason"] = llm_short
        out["copy_method"] = "llm"
        llm_conf = _safe_float(parsed.get("copy_confidence"), merged_conf)
        out["copy_confidence"] = round(_clamp((llm_conf * 0.6) + (merged_conf * 0.4), 0.35, 0.95), 2)
        out["copy_fallback_reason"] = ""
        return out
    except Exception as exc:
        out["copy_fallback_reason"] = str(exc or "llm_copy_failed")[:120]
        return out
