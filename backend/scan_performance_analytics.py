"""
Scan performance analytics – time-to-first-result, time-to-final-result, latency breakdown.
Events are best-effort, non-blocking; analytics failure must not break the scan path.
"""
from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

STORE_VERSION = "v1"
_MAX_EVENTS = 50000
_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    override = str(os.getenv("SCAN_PERFORMANCE_EVENTS_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "scan_performance_events.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": STORE_VERSION, "events": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", STORE_VERSION)
            data.setdefault("events", [])
            if isinstance(data.get("events"), list):
                return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, separators=(",", ":"), ensure_ascii=False)


def record_scan_performance_event(event: Dict[str, Any]) -> None:
    """
    Append a scan performance event. Best-effort, non-blocking.
    Callers must not rely on this for correctness; failures are swallowed.
    """
    if not event or not isinstance(event, dict):
        return
    row = dict(event)
    row.setdefault("created_at", _now_iso())
    try:
        with _LOCK:
            store = _load_store()
            events = store.get("events") or []
            if not isinstance(events, list):
                events = []
            events.append(row)
            if len(events) > _MAX_EVENTS:
                store["events"] = events[-_MAX_EVENTS:]
            else:
                store["events"] = events
            store["version"] = STORE_VERSION
            _save_store(store)
    except Exception:
        pass


def compute_percentiles(values: List[float]) -> Dict[str, float]:
    """
    Compute p50 (median) and p90 for a list of numeric values.
    Returns {"p50": ..., "p90": ...}; p90 may be 0 if insufficient data.
    """
    if not values:
        return {"p50": 0.0, "p90": 0.0}
    sorted_vals = sorted(float(v) for v in values if v is not None)
    if not sorted_vals:
        return {"p50": 0.0, "p90": 0.0}
    n = len(sorted_vals)
    p50_idx = (n - 1) // 2
    p90_idx = int((n - 1) * 0.9)
    return {
        "p50": round(float(sorted_vals[p50_idx]), 2),
        "p90": round(float(sorted_vals[p90_idx]), 2),
    }


def build_scan_performance_summary(window_days: int = 7) -> Dict[str, Any]:
    """
    Build a performance summary from events in the last window_days.
    Returns total_scans, median/p90 time_to_first_result_ms, time_to_final_result_ms,
    median vision_ms, nutrition_ms, meal_qa_ms, enrichment_ms, cache_hit_rate, etc.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max(1, int(window_days)))
    cutoff_iso = cutoff.isoformat()

    with _LOCK:
        store = _load_store()
        events = store.get("events") or []
        if not isinstance(events, list):
            events = []

    filtered = [
        e
        for e in events
        if isinstance(e, dict) and (e.get("created_at") or "") >= cutoff_iso
    ]

    total_scans = len(filtered)
    if total_scans == 0:
        return {
            "total_scans": 0,
            "window_days": window_days,
            "median_time_to_first_result_ms": 0.0,
            "median_time_to_final_result_ms": 0.0,
            "p90_time_to_first_result_ms": 0.0,
            "p90_time_to_final_result_ms": 0.0,
            "median_vision_ms": 0.0,
            "median_nutrition_ms": 0.0,
            "median_meal_qa_ms": 0.0,
            "median_enrichment_ms": 0.0,
            "median_resize_ms": 0.0,
            "median_priors_ms": 0.0,
            "cache_hit_rate": 0.0,
            "vision_cache_hit_rate": 0.0,
            "vision_cache_hit_count": 0,
            "vision_cache_miss_count": 0,
            "median_time_to_first_result_ms_when_vision_cache_hit": None,
            "median_time_to_first_result_ms_when_vision_cache_miss": None,
            "vision_cache_skipped_reasons": {},
            "average_image_resize_savings_pct": None,
        }

    def _collect(key: str) -> List[float]:
        return [
            float(e[key])
            for e in filtered
            if isinstance(e.get(key), (int, float)) and e[key] is not None
        ]

    ttfr = _collect("time_to_first_result_ms")
    ttfinal = _collect("time_to_final_result_ms")
    vision = _collect("vision_ms")
    nutrition = _collect("nutrition_ms")
    meal_qa = _collect("meal_qa_ms")
    enrichment = _collect("enrichment_ms")
    resize = _collect("resize_ms")
    priors = _collect("priors_ms")

    hit_count = sum(int(e.get("nutrition_cache_hit_count") or 0) for e in filtered)
    miss_count = sum(int(e.get("nutrition_cache_miss_count") or 0) for e in filtered)
    total_lookups = hit_count + miss_count
    cache_hit_rate = round(hit_count / total_lookups, 4) if total_lookups > 0 else 0.0

    vision_hits = sum(1 for e in filtered if e.get("vision_cache_reuse_used"))
    vision_cache_hit_rate = round(vision_hits / total_scans, 4) if total_scans > 0 else 0.0

    vision_cache_hit_count = sum(int(e.get("vision_cache_hit_count") or 0) for e in filtered)
    vision_cache_miss_count = sum(int(e.get("vision_cache_miss_count") or 0) for e in filtered)

    ttfr_when_hit = [float(e["time_to_first_result_ms"]) for e in filtered if e.get("vision_cache_reuse_used") and isinstance(e.get("time_to_first_result_ms"), (int, float))]
    ttfr_when_miss = [float(e["time_to_first_result_ms"]) for e in filtered if not e.get("vision_cache_reuse_used") and isinstance(e.get("time_to_first_result_ms"), (int, float))]
    median_ttfr_when_hit: Optional[float] = compute_percentiles(ttfr_when_hit)["p50"] if ttfr_when_hit else None
    median_ttfr_when_miss: Optional[float] = compute_percentiles(ttfr_when_miss)["p50"] if ttfr_when_miss else None

    vision_cache_skipped_reasons: Dict[str, int] = {}
    for e in filtered:
        r = str(e.get("vision_cache_skipped_reason") or "").strip()
        if r and r != "none":
            vision_cache_skipped_reasons[r] = vision_cache_skipped_reasons.get(r, 0) + 1

    resize_savings: List[float] = []
    for e in filtered:
        before_b = e.get("image_bytes_before")
        after_b = e.get("image_bytes_after")
        if isinstance(before_b, (int, float)) and before_b > 0 and isinstance(after_b, (int, float)):
            pct = 100.0 * (1.0 - (float(after_b) / float(before_b)))
            if 0 <= pct <= 100:
                resize_savings.append(pct)
    avg_resize_savings: Optional[float] = (
        round(sum(resize_savings) / len(resize_savings), 2) if resize_savings else None
    )

    return {
        "total_scans": total_scans,
        "window_days": window_days,
        "median_time_to_first_result_ms": compute_percentiles(ttfr)["p50"],
        "median_time_to_final_result_ms": compute_percentiles(ttfinal)["p50"],
        "p90_time_to_first_result_ms": compute_percentiles(ttfr)["p90"],
        "p90_time_to_final_result_ms": compute_percentiles(ttfinal)["p90"],
        "median_vision_ms": compute_percentiles(vision)["p50"],
        "median_nutrition_ms": compute_percentiles(nutrition)["p50"],
        "median_meal_qa_ms": compute_percentiles(meal_qa)["p50"],
        "median_enrichment_ms": compute_percentiles(enrichment)["p50"],
        "median_resize_ms": compute_percentiles(resize)["p50"],
        "median_priors_ms": compute_percentiles(priors)["p50"],
        "cache_hit_rate": cache_hit_rate,
        "vision_cache_hit_rate": vision_cache_hit_rate,
        "vision_cache_hit_count": vision_cache_hit_count,
        "vision_cache_miss_count": vision_cache_miss_count,
        "median_time_to_first_result_ms_when_vision_cache_hit": median_ttfr_when_hit,
        "median_time_to_first_result_ms_when_vision_cache_miss": median_ttfr_when_miss,
        "vision_cache_skipped_reasons": vision_cache_skipped_reasons,
        "average_image_resize_savings_pct": avg_resize_savings,
    }


def list_recent_events(limit: int = 50) -> List[Dict[str, Any]]:
    """
    Return the most recent scan performance events (newest first).
    """
    with _LOCK:
        store = _load_store()
        events = store.get("events") or []
        if not isinstance(events, list):
            events = []
    rev = list(reversed(events))
    return [dict(e) for e in rev[: max(1, int(limit))] if isinstance(e, dict)]
