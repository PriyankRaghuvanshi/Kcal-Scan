"""
Vision result cache for food scan pipeline.
Caches vision classification output for near-identical resized images to avoid repeated Gemini calls.
Reuse is conservative: only when confidence is sufficient and no signals suggest unsafe reuse.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

CACHE_VERSION = "v1"
DEFAULT_TTL_HOURS = 72
DEFAULT_MIN_CONFIDENCE = 0.72
_MAX_ITEMS_FOR_SAFE_REUSE = 8


def compute_image_fingerprint(image_bytes: bytes) -> str:
    """
    Deterministic fingerprint from image bytes (typically the resized scan image).
    SHA256 hex digest; stable for identical bytes.
    """
    if not image_bytes:
        return ""
    return hashlib.sha256(image_bytes).hexdigest()


def _cache_path() -> Path:
    override = str(os.getenv("VISION_RESULT_CACHE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "vision_result_cache.json"


def _now_utc() -> float:
    return time.time()


def get_cached_vision_result(fingerprint: str) -> Optional[Dict[str, Any]]:
    """
    Get cached vision result for a fingerprint.
    Returns None if miss or expired.
    """
    k = str(fingerprint or "").strip()
    if not k or len(k) < 8:
        return None
    path = _cache_path()
    if not path.exists():
        return None
    _lock = getattr(get_cached_vision_result, "_lock", None)
    if _lock is None:
        setattr(get_cached_vision_result, "_lock", threading.Lock())
        _lock = getattr(get_cached_vision_result, "_lock")
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as f:
                raw = f.read()
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            return None
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    entry = entries.get(k)
    if not isinstance(entry, dict):
        return None
    expires_at = float(entry.get("expires_at", 0) or 0)
    if expires_at <= 0 or _now_utc() > expires_at:
        return None
    return dict(entry)


def set_cached_vision_result(fingerprint: str, value: Dict[str, Any], ttl_hours: int = 72) -> None:
    """
    Store vision result for a fingerprint.
    value should include: items, top_candidates, vision_confidence, clarifying_question (optional),
    editable_context (optional).
    """
    k = str(fingerprint or "").strip()
    if not k or len(k) < 8:
        return
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    now = _now_utc()
    expires_at = now + (ttl_hours * 3600)
    entry = dict(value)
    entry["fingerprint"] = k
    entry["created_at"] = entry.get("created_at") or now
    entry["expires_at"] = expires_at
    entry["ttl_hours"] = ttl_hours
    _lock = getattr(set_cached_vision_result, "_lock", None)
    if _lock is None:
        setattr(set_cached_vision_result, "_lock", threading.Lock())
        _lock = getattr(set_cached_vision_result, "_lock")
    with _lock:
        try:
            if path.exists():
                try:
                    with path.open("r", encoding="utf-8") as f:
                        raw = f.read()
                    data = json.loads(raw) if raw.strip() else {}
                except Exception:
                    data = {}
            else:
                data = {}
            if not isinstance(data.get("entries"), dict):
                data["entries"] = {}
            data["entries"][k] = entry
            data["version"] = CACHE_VERSION
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"), ensure_ascii=False)
        except Exception:
            pass


def should_reuse_cached_vision_result(
    cached: Dict[str, Any],
    image_meta: Optional[Dict[str, Any]] = None,
    min_confidence: float = 0.72,
) -> bool:
    """
    Conservative rules for reusing a cached vision result.
    Returns True only when safe; otherwise False (fall back to full vision).

    Rules:
    - Cached vision_confidence >= min_confidence
    - Cached has non-empty items
    - Each item has name and grams > 0
    - Item count <= MAX_ITEMS_FOR_SAFE_REUSE (avoid mixed/complex ambiguous meals)
    - When in doubt, return False
    """
    _ = image_meta
    if not cached or not isinstance(cached, dict):
        return False
    conf = float(cached.get("vision_confidence", 0) or 0)
    if conf < min_confidence:
        return False
    items = cached.get("items") if isinstance(cached.get("items"), list) else []
    if not items:
        return False
    if len(items) > _MAX_ITEMS_FOR_SAFE_REUSE:
        return False
    for it in items:
        if not isinstance(it, dict):
            return False
        name = str(it.get("name") or "").strip()
        grams = float(it.get("grams", 0) or 0)
        if not name or grams <= 0:
            return False
    return True


def vision_cache_skipped_reason(cached: Dict[str, Any], min_confidence: float = 0.72) -> str:
    """Return a reason string when cached result should not be reused."""
    if not cached or not isinstance(cached, dict):
        return "no_cache"
    conf = float(cached.get("vision_confidence", 0) or 0)
    if conf < min_confidence:
        return "low_confidence"
    items = cached.get("items") if isinstance(cached.get("items"), list) else []
    if not items:
        return "no_items"
    if len(items) > _MAX_ITEMS_FOR_SAFE_REUSE:
        return "too_many_items"
    for it in items:
        if not isinstance(it, dict):
            return "invalid_items"
        name = str(it.get("name") or "").strip()
        grams = float(it.get("grams", 0) or 0)
        if not name or grams <= 0:
            return "invalid_items"
    return ""
