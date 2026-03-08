from __future__ import annotations

import json
import os
from typing import Any, Dict

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - may be unavailable in thin test envs.
    genai = None  # type: ignore[assignment]


LLM_COACH_PHRASING_VERSION = "v1"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_MAX_HEADLINE_WORDS = 9
_MAX_SUPPORTING_WORDS = 18
_MAX_HEADLINE_CHARS = 72
_MAX_SUPPORTING_CHARS = 120


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
        str(os.getenv("COACH_PHRASING_LLM_MODEL", "") or "").strip()
        or str(os.getenv("COACH_LLM_MODEL", "") or "").strip()
        or str(os.getenv("SCAN_LLM_MODEL", "") or "").strip()
        or "gemini-2.5-flash"
    )


def _timeout_sec() -> float:
    try:
        value = float(str(os.getenv("COACH_PHRASING_TIMEOUT_SEC", "3.5") or "3.5").strip())
    except Exception:
        value = 3.5
    return max(2.0, min(6.0, float(value)))


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
        data = json.loads(payload)
        return data if isinstance(data, dict) else None
    except Exception:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(payload[start : end + 1])
            return data if isinstance(data, dict) else None
        except Exception:
            return None
    return None


def _word_count(text: str) -> int:
    return len([part for part in _normalized(text).split(" ") if part])


def _validate_short_copy(headline: str, supporting_text: str) -> bool:
    if not headline or not supporting_text:
        return False
    if _word_count(headline) > _MAX_HEADLINE_WORDS:
        return False
    if _word_count(supporting_text) > _MAX_SUPPORTING_WORDS:
        return False
    if len(headline) > _MAX_HEADLINE_CHARS:
        return False
    if len(supporting_text) > _MAX_SUPPORTING_CHARS:
        return False
    return True


def _build_prompt(*, headline: str, supporting_text: str, context: Dict[str, Any]) -> str:
    tone = str(context.get("tone") or "calm").strip().lower()
    goal = str(context.get("goal") or "").strip().lower()
    decision = str(context.get("decision") or "").strip().upper()
    cut_mode = bool(context.get("cut_mode"))

    return (
        "Rewrite this nutrition coach microcopy.\n"
        "Return ONLY JSON:\n"
        '{"headline":"...", "supporting_text":"..."}\n'
        "Rules:\n"
        f"- Headline max {_MAX_HEADLINE_WORDS} words.\n"
        f"- Supporting text max {_MAX_SUPPORTING_WORDS} words.\n"
        "- Keep meaning the same as input.\n"
        "- Tone: calm, smart, practical.\n"
        "- No hype, no jargon, no wellness fluff.\n"
        "- No markdown.\n"
        f"Context: tone={tone}, goal={goal or 'none'}, decision={decision or 'none'}, cut_mode={str(cut_mode).lower()}.\n"
        f"Input headline: {headline}\n"
        f"Input supporting_text: {supporting_text}\n"
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


def maybe_rephrase_coach_message(
    *,
    headline: str,
    supporting_text: str,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    base_headline = _normalized(headline)
    base_supporting = _normalized(supporting_text)
    ctx = context if isinstance(context, dict) else {}

    out = {
        "headline": base_headline,
        "supporting_text": base_supporting,
        "phrasing_method": "deterministic",
        "phrasing_version": LLM_COACH_PHRASING_VERSION,
        "phrasing_attempted": False,
        "phrasing_fallback_reason": "",
    }

    if not _env_bool("ENABLE_LLM_COACH_PHRASING", default=False):
        return out
    if not _llm_available():
        out["phrasing_attempted"] = True
        out["phrasing_fallback_reason"] = "llm_unavailable"
        return out

    out["phrasing_attempted"] = True
    try:
        prompt = _build_prompt(headline=base_headline, supporting_text=base_supporting, context=ctx)
        raw = _invoke_llm(prompt)
        parsed = _extract_json(raw)
        if not isinstance(parsed, dict):
            out["phrasing_fallback_reason"] = "invalid_llm_json"
            return out

        llm_headline = _normalized(parsed.get("headline"))
        llm_supporting = _normalized(parsed.get("supporting_text"))
        if not _validate_short_copy(llm_headline, llm_supporting):
            out["phrasing_fallback_reason"] = "output_too_long_or_invalid"
            return out

        out["headline"] = llm_headline
        out["supporting_text"] = llm_supporting
        out["phrasing_method"] = "llm"
        out["phrasing_fallback_reason"] = ""
        return out
    except Exception as exc:
        out["phrasing_fallback_reason"] = str(exc or "llm_phrase_failed")[:120]
        return out

