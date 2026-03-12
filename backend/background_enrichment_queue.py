"""
Background enrichment queue: scaffold for enqueueing places for later enrichment.
No workers/schedulers yet. Structure only for enqueue + list + mark processed.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

REASONS = (
    "high_visibility",
    "repeatedly_fetched",
    "user_clicked",
    "candidate_low_specificity",
    "missing_chain_support",
    "high_visibility_generic",
    "user_clicked_generic",
    "missing_local_profile",
    "diet_safe_but_low_specificity",
    "missing_veg_profile",
    "missing_vegan_profile",
    "unknown_suburb_visible_result",
    "user_correction_high_signal",
    "vegan_option_repeated",
    "vegetarian_option_repeated",
    "better_order_repeated",
    "conflict_needs_review",
)
STATUSES = ("pending", "processing", "processed", "failed")


def _queue_path() -> Path:
    override = str(os.getenv("BACKGROUND_ENRICHMENT_QUEUE_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "enrichment_queue.json"


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def enqueue(
    place_id: str,
    *,
    place_name: str = "",
    place_types: Optional[List[str]] = None,
    chain_match_key: Optional[str] = None,
    market: str = "",
    reason_enqueued: str = "high_visibility",
) -> Dict[str, Any]:
    """
    Enqueue a place for background enrichment.
    Returns the created record.
    """
    pid = str(place_id or "").strip()
    if not pid:
        return {}
    if reason_enqueued not in REASONS:
        reason_enqueued = "high_visibility"
    record = {
        "place_id": pid,
        "place_name": str(place_name or "").strip(),
        "place_types": list(place_types)[:20] if place_types else [],
        "chain_match_key": str(chain_match_key) if chain_match_key else None,
        "market": str(market or "").strip(),
        "reason_enqueued": reason_enqueued,
        "created_at": _now_iso(),
        "processed_at": None,
        "status": "pending",
    }
    path = _queue_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    _lock = getattr(enqueue, "_lock", None)
    if _lock is None:
        setattr(enqueue, "_lock", threading.Lock())
        _lock = getattr(enqueue, "_lock")
    with _lock:
        data = {"version": "v1", "records": []}
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        records = data.get("records") if isinstance(data.get("records"), list) else []
        existing_ids = {r.get("place_id") for r in records if isinstance(r, dict)}
        if pid not in existing_ids:
            records.append(record)
            data["records"] = records
            try:
                with path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
    return record


def list_pending(limit: int = 100) -> List[Dict[str, Any]]:
    """List records with status=pending."""
    path = _queue_path()
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []
    records = data.get("records") if isinstance(data.get("records"), list) else []
    pending = [r for r in records if isinstance(r, dict) and r.get("status") == "pending"]
    return pending[:limit]


def mark_processed(place_id: str, *, status: str = "processed") -> bool:
    """Mark a record as processed or failed."""
    pid = str(place_id or "").strip()
    if not pid or status not in ("processed", "failed"):
        return False
    path = _queue_path()
    if not path.exists():
        return False
    _lock = getattr(mark_processed, "_lock", None)
    if _lock is None:
        setattr(mark_processed, "_lock", threading.Lock())
        _lock = getattr(mark_processed, "_lock")
    with _lock:
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return False
        records = data.get("records") if isinstance(data.get("records"), list) else []
        found = False
        for r in records:
            if isinstance(r, dict) and str(r.get("place_id") or "") == pid:
                r["processed_at"] = _now_iso()
                r["status"] = status
                found = True
                break
        if found:
            data["records"] = records
            try:
                with path.open("w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
            except Exception:
                pass
        return found


def was_recently_enqueued(place_id: str, within_hours: float = 24.0) -> bool:
    """True if place was enqueued within the last N hours. Avoids queue spam."""
    pid = str(place_id or "").strip()
    if not pid:
        return False
    path = _queue_path()
    if not path.exists():
        return False
    try:
        import time
        from datetime import datetime
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        records = data.get("records") if isinstance(data.get("records"), list) else []
        cutoff = time.time() - (within_hours * 3600)
        for r in records:
            if isinstance(r, dict) and str(r.get("place_id") or "").strip() == pid:
                created = r.get("created_at") or ""
                if created:
                    try:
                        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                        ts = dt.timestamp()
                        if ts >= cutoff:
                            return True
                    except Exception:
                        pass
        return False
    except Exception:
        return False


def should_enqueue_for_low_specificity(place: Dict[str, Any]) -> bool:
    """
    True if place reached top results with only generic/heuristic fallback.
    Used to decide when to enqueue for background enrichment.
    """
    tier = str(place.get("chosen_candidate_specificity_tier") or "").strip()
    source = str(place.get("menu_item_source") or place.get("best_item_source") or "").strip().lower()
    if tier in ("exact_menu_match", "chain_registry", "menu_inferred"):
        return False
    if source in ("real_menu", "user_scan", "chain_registry"):
        return False
    return True
