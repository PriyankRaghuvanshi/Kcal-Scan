"""
Venue intelligence cache for Healthy Nearby fast path.
Stores pre-computed menu/candidate data so we avoid redundant work on repeated requests.
Priority: exact cache > chain registry > enriched local venue > heuristic fallback.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

CACHE_VERSION = "v2"  # v2: provenance fields persisted; v1 rows invalidated on read
DEFAULT_TTL_SEC = 86400 * 7  # 7 days


def _cache_path() -> Path:
    override = str(os.getenv("VENUE_INTELLIGENCE_CACHE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "venue_intelligence_cache.json"


def _now() -> float:
    return time.time()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def get(place_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cached intelligence for a place_id.
    Returns None if miss or expired.
    """
    pid = str(place_id or "").strip()
    if not pid:
        return None
    path = _cache_path()
    if not path.exists():
        return None
    _lock = getattr(get, "_lock", None)
    if _lock is None:
        setattr(get, "_lock", threading.Lock())
        _lock = getattr(get, "_lock")
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
    # Reject entries written under an older cache version. Provenance schema changed
    # in v2; v1 rows lack item_provenance/covered_chain_key and would serve stale fallback.
    if str(data.get("version") or "") != CACHE_VERSION:
        return None
    entries = data.get("entries") if isinstance(data.get("entries"), dict) else {}
    entry = entries.get(pid)
    if not isinstance(entry, dict):
        return None
    ttl = _safe_float(entry.get("ttl_sec"), DEFAULT_TTL_SEC)
    enriched_at = _safe_float(entry.get("last_enriched_at"), 0.0)
    if enriched_at <= 0 or (_now() - enriched_at) > ttl:
        return None
    return dict(entry)


def get_by_chain_key(chain_key: str) -> Optional[Dict[str, Any]]:
    """
    Get cached chain-level intelligence (e.g. from prior chain lookup).
    Chain registry is the source of truth for chain items; this cache
    stores resolved results to avoid repeated parsing.
    """
    key = str(chain_key or "").strip().lower()
    if not key:
        return None
    path = _cache_path()
    if not path.exists():
        return None
    _lock = getattr(get_by_chain_key, "_lock", None)
    if _lock is None:
        setattr(get_by_chain_key, "_lock", threading.Lock())
        _lock = getattr(get_by_chain_key, "_lock")
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return None
    chain_entries = data.get("chain_entries") if isinstance(data.get("chain_entries"), dict) else {}
    entry = chain_entries.get(key)
    if not isinstance(entry, dict):
        return None
    return dict(entry)


def put(
    place_id: str,
    *,
    candidates: List[Dict[str, Any]],
    specificity_tier: str = "heuristic_cuisine_match_weak",
    confidence: float = 0.5,
    source_type: str = "enriched_local",
    chain_key: Optional[str] = None,
    chain_match: bool = False,
    swap_templates: Optional[List[Dict[str, Any]]] = None,
    item_provenance: Optional[str] = None,
    covered_chain_key: Optional[str] = None,
    covered_chain_neutral: bool = False,
    can_show_verified_badge: bool = False,
    covered_chain_display_name: Optional[str] = None,
    covered_chain_menu_url: Optional[str] = None,
) -> None:
    """Store venue intelligence for a place. Creates file if missing."""
    pid = str(place_id or "").strip()
    if not pid:
        return
    path = _cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "place_id": pid,
        "candidates": candidates[:12] if candidates else [],
        "specificity_tier": str(specificity_tier or "heuristic_cuisine_match_weak"),
        "confidence": round(float(confidence), 2),
        "source_type": str(source_type or "enriched_local"),
        "chain_key": str(chain_key) if chain_key else None,
        "chain_match": bool(chain_match),
        "last_enriched_at": _now(),
        "ttl_sec": DEFAULT_TTL_SEC,
        "swap_templates": swap_templates[:5] if swap_templates else [],
        "item_provenance": str(item_provenance) if item_provenance else None,
        "covered_chain_key": str(covered_chain_key).strip().lower() if covered_chain_key else None,
        "covered_chain_neutral": bool(covered_chain_neutral),
        "can_show_verified_badge": bool(can_show_verified_badge),
        "covered_chain_display_name": str(covered_chain_display_name) if covered_chain_display_name else None,
        "covered_chain_menu_url": str(covered_chain_menu_url) if covered_chain_menu_url else None,
    }
    _lock = getattr(put, "_lock", None)
    if _lock is None:
        setattr(put, "_lock", threading.Lock())
        _lock = getattr(put, "_lock")
    with _lock:
        data = {"version": CACHE_VERSION, "entries": {}, "chain_entries": {}}
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        # Reset entries when file version is stale to avoid mixing old/new schemas.
        if str(data.get("version") or "") != CACHE_VERSION:
            data = {"version": CACHE_VERSION, "entries": {}, "chain_entries": {}}
        if not isinstance(data.get("entries"), dict):
            data["entries"] = {}
        data["entries"][pid] = entry
        try:
            with path.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass


def has(place_id: str) -> bool:
    """Quick check if we have valid cached intelligence."""
    return get(place_id) is not None


def _normalize_candidate_to_menu_item(c: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize candidate (chain or cuisine shape) to top_menu_item shape."""
    name = str(c.get("item_name") or c.get("candidate_name") or "").strip()
    cal = int(c.get("estimated_calories") or 520)
    pro = int(c.get("estimated_protein_g") or 28)
    return {
        "item_name": name or "Lighter menu option",
        "estimated_calories": cal,
        "estimated_protein_g": pro,
        "menu_item_source": str(c.get("menu_item_source") or c.get("source_type") or "enriched_local"),
        "menu_item_confidence": float(c.get("menu_item_confidence") or c.get("confidence") or 0.6),
    }


def cache_to_menu_payload(cached: Dict[str, Any], place: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert cached entry to the shape expected by downstream (menu_recommendations).
    """
    raw = cached.get("candidates") or []
    items = [_normalize_candidate_to_menu_item(c) for c in raw if isinstance(c, dict)]
    top = items[0] if items else {}
    # Preserve provenance verbatim. Legacy rows without these fields get conservative defaults —
    # never auto-promote to exact_chain_menu / verified badge.
    stored_provenance = cached.get("item_provenance")
    return {
        "menu_item_scoring_available": bool(items),
        "menu_items_source": cached.get("source_type") or "enriched_local",
        "menu_source": cached.get("source_type") or "enriched_local",
        "menu_confidence": cached.get("confidence", 0.5),
        "extraction_method": "venue_intelligence_cache",
        "parse_method": "cache",
        "source_url": "",
        "top_menu_items": items[:3],
        "best_menu_items": items[:3],
        "top_menu_item": top,
        "top_item": str(top.get("item_name") or ""),
        "chain_key": cached.get("chain_key"),
        "chain_match": cached.get("chain_match", False),
        "from_venue_cache": True,
        "item_provenance": str(stored_provenance) if stored_provenance else None,
        "covered_chain_key": cached.get("covered_chain_key"),
        "covered_chain_neutral": bool(cached.get("covered_chain_neutral", False)),
        "can_show_verified_badge": bool(cached.get("can_show_verified_badge", False)),
        "covered_chain_display_name": cached.get("covered_chain_display_name") or "",
        "covered_chain_menu_url": cached.get("covered_chain_menu_url") or "",
    }
