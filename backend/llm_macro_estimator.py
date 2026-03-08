from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - may be unavailable in slim test envs.
    genai = None  # type: ignore[assignment]


LLM_MACRO_ESTIMATION_VERSION = "v1"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_VALID_SATIETY = {"low", "medium", "high"}
_UNUSUAL_TOKENS = {
    "fusion",
    "supreme",
    "monster",
    "ultimate",
    "fiesta",
    "special",
    "signature",
    "stacked",
    "loaded",
}


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return _normalized(raw) in _TRUE_VALUES


def _llm_available() -> bool:
    return bool(genai is not None) and bool(str(os.getenv("GEMINI_API_KEY", "") or "").strip())


def _model_name() -> str:
    return (
        str(os.getenv("LLM_MACRO_MODEL", "") or "").strip()
        or str(os.getenv("SCAN_LLM_MODEL", "") or "").strip()
        or str(os.getenv("GEMINI_MODEL", "") or "").strip()
        or "gemini-2.5-flash"
    )


def _timeout_sec() -> float:
    try:
        val = float(str(os.getenv("LLM_MACRO_TIMEOUT_SEC", "4") or "4").strip())
    except Exception:
        val = 4.0
    return _clamp(val, 2.0, 8.0)


def _confidence_threshold() -> float:
    try:
        val = float(str(os.getenv("LLM_MACRO_MIN_CONFIDENCE", "0.64") or "0.64").strip())
    except Exception:
        val = 0.64
    return _clamp(val, 0.35, 0.9)


def _extract_place_types(place: Dict[str, Any] | None) -> List[str]:
    payload = place if isinstance(place, dict) else {}
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    out = []
    for token in types:
        normalized = _normalized(token).replace(" ", "_")
        if normalized:
            out.append(normalized)
    return out[:6]


def _is_unusual_item(item_name: str, profile_hit_count: int) -> bool:
    text = _normalized(item_name)
    if not text:
        return True
    words = text.split()
    if profile_hit_count <= 0 and len(words) <= 2:
        return True
    if any(token in text for token in _UNUSUAL_TOKENS):
        return True
    if sum(ch.isdigit() for ch in text) > 2:
        return True
    return False


def _strip_fences(text: str) -> str:
    payload = str(text or "").strip()
    if payload.startswith("```json"):
        payload = payload[len("```json") :].strip()
    if payload.startswith("```"):
        payload = payload[len("```") :].strip()
    if payload.endswith("```"):
        payload = payload[:-3].strip()
    return payload


def _extract_json_payload(text: str) -> Any:
    payload = _strip_fences(text)
    if not payload:
        return None
    try:
        return json.loads(payload)
    except Exception:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        snippet = payload[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None
    return None


def _build_prompt(
    *,
    item_name: str,
    cuisine_hint: str,
    place_types: List[str],
    known_components: List[str],
    deterministic_estimate: Dict[str, Any],
) -> str:
    safe_item = str(item_name or "").strip()[:180]
    safe_cuisine = str(cuisine_hint or "").strip()[:80]
    place_type_text = ", ".join(place_types[:6]) if place_types else "unknown"
    components_text = ", ".join(known_components[:10]) if known_components else "unknown"

    det_kcal = int(_safe_float(deterministic_estimate.get("estimated_calories"), 520) or 520)
    det_protein = int(_safe_float(deterministic_estimate.get("estimated_protein_g"), 30) or 30)
    det_carbs = int(_safe_float(deterministic_estimate.get("estimated_carbs_g"), 46) or 46)
    det_fat = int(_safe_float(deterministic_estimate.get("estimated_fat_g"), 18) or 18)

    return (
        "Estimate realistic meal macros for one restaurant menu item.\n"
        "Return ONLY JSON with fields:\n"
        "{"
        '"estimated_calories": number,'
        '"estimated_protein_g": number,'
        '"estimated_carbs_g": number,'
        '"estimated_fat_g": number,'
        '"estimated_satiety": "low|medium|high",'
        '"macro_confidence": number'
        "}\n"
        "No markdown. No extra keys.\n"
        "Use practical restaurant portions.\n"
        f"item_name: {safe_item}\n"
        f"cuisine_hint: {safe_cuisine or 'unknown'}\n"
        f"place_types: {place_type_text}\n"
        f"known_components: {components_text}\n"
        f"heuristic_anchor: calories={det_kcal}, protein={det_protein}, carbs={det_carbs}, fat={det_fat}\n"
    )


def _invoke_llm_response_text(prompt: str) -> str:
    if not _llm_available():
        raise RuntimeError("llm_unavailable")

    api_key = str(os.getenv("GEMINI_API_KEY", "") or "").strip()
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(_model_name())
    response = model.generate_content(
        prompt,
        generation_config={"temperature": 0.1, "response_mime_type": "application/json"},
        request_options={"timeout": float(_timeout_sec())},
    )
    return str(getattr(response, "text", "") or "").strip()


def _sanitize_llm_estimate(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    calories = int(round(_clamp(_safe_float(payload.get("estimated_calories"), -1), 280.0, 1300.0)))
    protein_g = int(round(_clamp(_safe_float(payload.get("estimated_protein_g"), -1), 8.0, 95.0)))
    carbs_g = int(round(_clamp(_safe_float(payload.get("estimated_carbs_g"), -1), 8.0, 180.0)))
    fat_g = int(round(_clamp(_safe_float(payload.get("estimated_fat_g"), -1), 5.0, 85.0)))
    satiety = _normalized(payload.get("estimated_satiety"))
    confidence = round(_clamp(_safe_float(payload.get("macro_confidence"), 0.6), 0.35, 0.92), 2)

    if satiety not in _VALID_SATIETY:
        if protein_g >= 35 and calories <= 650:
            satiety = "high"
        elif protein_g >= 22 and calories <= 850:
            satiety = "medium"
        else:
            satiety = "low"

    # Quick plausibility guardrail: reject absurdly inconsistent energy totals.
    estimated_energy = (4 * protein_g) + (4 * carbs_g) + (9 * fat_g)
    if estimated_energy < 220 or estimated_energy > 1900:
        return None

    return {
        "estimated_calories": calories,
        "estimated_protein_g": protein_g,
        "estimated_carbs_g": carbs_g,
        "estimated_fat_g": fat_g,
        "estimated_satiety": satiety,
        "macro_confidence": confidence,
    }


def maybe_estimate_unknown_meal_macros(
    *,
    item_name: str,
    cuisine_hint: str = "",
    place: Dict[str, Any] | None = None,
    known_components: Optional[List[str]] = None,
    deterministic_estimate: Dict[str, Any] | None = None,
    has_known_nutrition: bool = False,
    profile_hit_count: int = 0,
) -> Dict[str, Any]:
    baseline = deterministic_estimate if isinstance(deterministic_estimate, dict) else {}
    baseline_conf = float(_safe_float(baseline.get("macro_confidence"), 0.0) or 0.0)
    unusual_item = _is_unusual_item(item_name=item_name, profile_hit_count=int(profile_hit_count or 0))

    should_attempt = (
        _env_bool("ENABLE_LLM_MACRO_ESTIMATION", default=False)
        and not has_known_nutrition
        and (baseline_conf < _confidence_threshold() or unusual_item)
    )

    if not should_attempt:
        return {"attempted": False, "used": False, "error": "", "estimate": None}

    if not _llm_available():
        return {"attempted": True, "used": False, "error": "llm_unavailable", "estimate": None}

    try:
        prompt = _build_prompt(
            item_name=item_name,
            cuisine_hint=cuisine_hint,
            place_types=_extract_place_types(place),
            known_components=list(known_components or []),
            deterministic_estimate=baseline,
        )
        raw_response = _invoke_llm_response_text(prompt)
        if not raw_response:
            return {"attempted": True, "used": False, "error": "empty_llm_response", "estimate": None}

        parsed = _extract_json_payload(raw_response)
        if not isinstance(parsed, dict):
            return {"attempted": True, "used": False, "error": "invalid_llm_json", "estimate": None}

        estimate = _sanitize_llm_estimate(parsed)
        if not isinstance(estimate, dict):
            return {"attempted": True, "used": False, "error": "invalid_llm_values", "estimate": None}

        return {
            "attempted": True,
            "used": True,
            "error": "",
            "estimate": estimate,
            "estimation_method": "llm",
            "estimation_version": LLM_MACRO_ESTIMATION_VERSION,
        }
    except Exception as exc:
        return {"attempted": True, "used": False, "error": str(exc or "llm_macro_failed")[:220], "estimate": None}

