"""Lightweight UPF quick-scan helpers (keeps tests importable without full app stack)."""

from typing import Any, Dict, Optional

import coach_daily_logic as coach_logic


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_float(x: Any, default: Optional[float] = None) -> Optional[float]:
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def parse_upf_quick_model_output(text: str) -> float:
    parsed = coach_logic.extract_json_object(str(text or "").strip())
    if not isinstance(parsed, dict):
        raise ValueError("upf_quick_no_json")
    raw = parsed.get("ultra_processed_score")
    if raw is None:
        raise ValueError("upf_quick_missing_score")
    score = float(_safe_float(raw, None) or 0.0)
    return float(_clamp(score, 0.0, 10.0))
