from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


RECOMMENDATION_FEEDBACK_VERSION = "v1"

EVENT_RECOMMENDATION_VIEWED = "recommendation_viewed"
EVENT_RECOMMENDATION_SELECTED = "recommendation_selected"
EVENT_MEAL_SCANNED = "meal_scanned"
EVENT_RECOMMENDATION_FOLLOWED = "recommendation_followed"
EVENT_RECOMMENDATION_FEEDBACK = "recommendation_feedback"

# Lightweight funnel extensions for lunch decision + social proof flows.
EVENT_RECOMMENDATION_SHOWN = "recommendation_shown"
EVENT_RECOMMENDATION_CLICKED = "recommendation_clicked"
EVENT_PLACE_SELECTED = "place_selected"
EVENT_SHARE_CARD_OPENED = "share_card_opened"
EVENT_SHARE_ACTION_TRIGGERED = "share_action_triggered"

ALLOWED_FEEDBACK_EVENTS = {
    EVENT_RECOMMENDATION_VIEWED,
    EVENT_RECOMMENDATION_SELECTED,
    EVENT_MEAL_SCANNED,
    EVENT_RECOMMENDATION_FOLLOWED,
    EVENT_RECOMMENDATION_FEEDBACK,
    EVENT_RECOMMENDATION_SHOWN,
    EVENT_RECOMMENDATION_CLICKED,
    EVENT_PLACE_SELECTED,
    EVENT_SHARE_CARD_OPENED,
    EVENT_SHARE_ACTION_TRIGGERED,
}

_MAX_EVENTS = 5000
_STORE_LOCK = threading.Lock()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(float(v))
    except Exception:
        return int(default)


def _normalize_yes_no_not_sure(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if not s:
        return None
    s = s.replace("-", "_").replace(" ", "_")
    if s in ("yes", "y"):
        return "yes"
    if s in ("no", "n"):
        return "no"
    if s in ("not_sure", "notsure", "unsure", "maybe", "idk"):
        return "not_sure"
    return None


def _normalize_yes_no(v: Any) -> str | None:
    s = str(v or "").strip().lower()
    if not s:
        return None
    s = s.replace("-", "_").replace(" ", "_")
    if s in ("yes", "y"):
        return "yes"
    if s in ("no", "n"):
        return "no"
    return None


def _init_user_feedback_counts() -> Dict[str, Any]:
    return {
        "available": {"yes": 0, "no": 0, "not_sure": 0},
        "ordered": {"yes": 0, "no": 0},
        "sauce_default": {"yes": 0, "no": 0, "not_sure": 0},
        "portion_standard": {"yes": 0, "no": 0, "not_sure": 0},
    }


def _confidence_from_yes_no_not_sure(counts: Dict[str, Any]) -> float:
    yes = _safe_int(counts.get("yes"), 0)
    no = _safe_int(counts.get("no"), 0)
    not_sure = _safe_int(counts.get("not_sure"), 0)
    definitive = yes + no
    uncertain = not_sure
    if definitive <= 0:
        return 0.0
    base = float(yes / definitive) if definitive > 0 else 0.0
    coverage = float(definitive / (definitive + uncertain)) if (definitive + uncertain) > 0 else 0.0
    return _clamp(base * coverage, 0.0, 1.0)


def _confidence_from_yes_no(counts: Dict[str, Any]) -> float:
    yes = _safe_int(counts.get("yes"), 0)
    no = _safe_int(counts.get("no"), 0)
    denom = yes + no
    if denom <= 0:
        return 0.0
    return _clamp(float(yes / denom), 0.0, 1.0)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_event_name(event: Any) -> str:
    return " ".join(str(event or "").strip().lower().split())


def _normalize_item_name(item: Any) -> str:
    return " ".join(str(item or "").strip().split())


def _item_key(item: Any) -> str:
    norm = " ".join(str(item or "").strip().lower().split())
    return norm if norm else "__place_level__"


def _store_path() -> Path:
    override = str(os.getenv("RECOMMENDATION_FEEDBACK_STORE_PATH", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "recommendation_feedback_store.json"


def _empty_store() -> Dict[str, Any]:
    return {
        "version": RECOMMENDATION_FEEDBACK_VERSION,
        "events": [],
        "aggregates": {},
    }


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()

    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", RECOMMENDATION_FEEDBACK_VERSION)
            data.setdefault("events", [])
            data.setdefault("aggregates", {})
            if isinstance(data.get("events"), list) and isinstance(data.get("aggregates"), dict):
                return data
    except Exception:
        pass

    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def _aggregate_key(place_id: str, item: Any) -> str:
    return f"{place_id}::{_item_key(item)}"


def _compute_rates(counts: Dict[str, int]) -> Dict[str, float]:
    # Accept both original and new funnel event names to keep scoring robust.
    viewed = int(_safe_float(counts.get(EVENT_RECOMMENDATION_VIEWED), 0) or 0) + int(
        _safe_float(counts.get(EVENT_RECOMMENDATION_SHOWN), 0) or 0
    )
    selected = int(_safe_float(counts.get(EVENT_RECOMMENDATION_SELECTED), 0) or 0) + int(
        _safe_float(counts.get(EVENT_RECOMMENDATION_CLICKED), 0) or 0
    ) + int(_safe_float(counts.get(EVENT_PLACE_SELECTED), 0) or 0)
    scanned = int(_safe_float(counts.get(EVENT_MEAL_SCANNED), 0) or 0)
    followed = int(_safe_float(counts.get(EVENT_RECOMMENDATION_FOLLOWED), 0) or 0)

    selection_rate = float(selected / viewed) if viewed > 0 else 0.0
    follow_rate = float(followed / selected) if selected > 0 else 0.0
    scan_after_selection_rate = float(scanned / selected) if selected > 0 else 0.0

    evidence_n = viewed + selected + followed
    signal_confidence = _clamp(evidence_n / 25.0, 0.0, 1.0)

    success_score = (
        (selection_rate * 0.35)
        + (follow_rate * 0.45)
        + (scan_after_selection_rate * 0.20)
    )

    score_adjustment = (success_score - 0.42) * 14.0 * signal_confidence
    score_adjustment = _clamp(score_adjustment, -6.0, 8.0)

    return {
        "selection_rate": round(selection_rate, 3),
        "follow_rate": round(follow_rate, 3),
        "scan_after_selection_rate": round(scan_after_selection_rate, 3),
        "success_score": round(success_score, 3),
        "signal_confidence": round(signal_confidence, 3),
        "score_adjustment": round(score_adjustment, 3),
    }


def _update_aggregate(
    store: Dict[str, Any],
    *,
    place_id: str,
    item: str,
    event: str,
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    key = _aggregate_key(place_id, item)
    aggregates = store.setdefault("aggregates", {})
    current = aggregates.get(key) if isinstance(aggregates.get(key), dict) else {}
    counts = current.get("counts") if isinstance(current.get("counts"), dict) else {}
    user_feedback_counts = (
        current.get("user_feedback_counts") if isinstance(current.get("user_feedback_counts"), dict) else {}
    )
    if not user_feedback_counts:
        user_feedback_counts = _init_user_feedback_counts()

    for ev in ALLOWED_FEEDBACK_EVENTS:
        counts[ev] = int(_safe_float(counts.get(ev), 0) or 0)

    counts[event] = counts.get(event, 0) + 1

    user_feedback_events_count = int(_safe_float(current.get("user_feedback_events_count"), 0) or 0)
    if event == EVENT_RECOMMENDATION_FEEDBACK and isinstance(metadata, dict):
        updated_any = False

        available = _normalize_yes_no_not_sure(metadata.get("available"))
        if available:
            user_feedback_counts.setdefault("available", {"yes": 0, "no": 0, "not_sure": 0})
            user_feedback_counts["available"][available] = int(
                _safe_int(user_feedback_counts["available"].get(available), 0) + 1
            )
            updated_any = True

        ordered = _normalize_yes_no(metadata.get("ordered"))
        if ordered:
            user_feedback_counts.setdefault("ordered", {"yes": 0, "no": 0})
            user_feedback_counts["ordered"][ordered] = int(
                _safe_int(user_feedback_counts["ordered"].get(ordered), 0) + 1
            )
            updated_any = True

        sauce_default = _normalize_yes_no_not_sure(metadata.get("sauce_default"))
        if sauce_default:
            user_feedback_counts.setdefault("sauce_default", {"yes": 0, "no": 0, "not_sure": 0})
            user_feedback_counts["sauce_default"][sauce_default] = int(
                _safe_int(user_feedback_counts["sauce_default"].get(sauce_default), 0) + 1
            )
            updated_any = True

        portion_standard = _normalize_yes_no_not_sure(metadata.get("portion_standard"))
        if portion_standard:
            user_feedback_counts.setdefault("portion_standard", {"yes": 0, "no": 0, "not_sure": 0})
            user_feedback_counts["portion_standard"][portion_standard] = int(
                _safe_int(user_feedback_counts["portion_standard"].get(portion_standard), 0) + 1
            )
            updated_any = True

        if updated_any:
            user_feedback_events_count += 1

    rates = _compute_rates(counts)
    events_count = sum(
        int(_safe_float(v, 0) or 0)
        for v in [
            counts.get(EVENT_RECOMMENDATION_VIEWED, 0),
            counts.get(EVENT_RECOMMENDATION_SHOWN, 0),
            counts.get(EVENT_RECOMMENDATION_SELECTED, 0),
            counts.get(EVENT_RECOMMENDATION_CLICKED, 0),
            counts.get(EVENT_PLACE_SELECTED, 0),
            counts.get(EVENT_MEAL_SCANNED, 0),
            counts.get(EVENT_RECOMMENDATION_FOLLOWED, 0),
            counts.get(EVENT_SHARE_CARD_OPENED, 0),
            counts.get(EVENT_SHARE_ACTION_TRIGGERED, 0),
        ]
    )

    aggregate = {
        "place_id": place_id,
        "item": _normalize_item_name(item),
        "item_key": _item_key(item),
        "events_count": int(events_count),
        "counts": counts,
        "selection_rate": rates["selection_rate"],
        "follow_rate": rates["follow_rate"],
        "scan_after_selection_rate": rates["scan_after_selection_rate"],
        "success_score": rates["success_score"],
        "signal_confidence": rates["signal_confidence"],
        "score_adjustment": rates["score_adjustment"],
        # Additive user-confirmed branch intelligence (kept separate from ranking math).
        "user_feedback_events_count": int(user_feedback_events_count),
        "user_feedback_counts": user_feedback_counts,
        "availability_confidence": round(
            _confidence_from_yes_no_not_sure(user_feedback_counts.get("available") or {}), 3
        ),
        "order_confirmation_rate": round(
            _confidence_from_yes_no(user_feedback_counts.get("ordered") or {}), 3
        ),
        "sauce_default_confidence": round(
            _confidence_from_yes_no_not_sure(user_feedback_counts.get("sauce_default") or {}), 3
        ),
        "portion_reliability": round(
            _confidence_from_yes_no_not_sure(user_feedback_counts.get("portion_standard") or {}), 3
        ),
        "user_feedback_confidence_source": "user_confirmations",
        "last_updated": _now_iso(),
    }

    aggregates[key] = aggregate
    return aggregate


def log_recommendation_feedback_event(
    *,
    event: Any,
    place_id: Any,
    item: Any = "",
    user_id: Any = "",
    session_id: Any = "",
    metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any] | None:
    event_name = _normalize_event_name(event)
    canonical_place_id = str(place_id or "").strip()
    item_name = _normalize_item_name(item)

    if not canonical_place_id or event_name not in ALLOWED_FEEDBACK_EVENTS:
        return None

    row = {
        "event_id": str(uuid.uuid4()),
        "event": event_name,
        "place_id": canonical_place_id,
        "item": item_name,
        "item_key": _item_key(item_name),
        "user_id": str(user_id or "").strip(),
        "session_id": str(session_id or "").strip(),
        "metadata": dict(metadata or {}),
        "created_at": _now_iso(),
    }

    with _STORE_LOCK:
        store = _load_store()
        events = store.setdefault("events", [])
        if not isinstance(events, list):
            events = []
            store["events"] = events

        events.append(row)
        if len(events) > _MAX_EVENTS:
            store["events"] = events[-_MAX_EVENTS:]

        # Update place+item aggregate.
        aggregate_item = _update_aggregate(
            store,
            place_id=canonical_place_id,
            item=item_name,
            event=event_name,
            metadata=metadata,
        )
        # Also update place-level aggregate for fallback signals.
        _update_aggregate(
            store,
            place_id=canonical_place_id,
            item="",
            event=event_name,
            metadata=metadata,
        )

        store["version"] = RECOMMENDATION_FEEDBACK_VERSION
        _save_store(store)

    out = dict(row)
    out["aggregate"] = aggregate_item
    return out


def get_feedback_summary(place_id: Any = "", item: Any = "") -> Dict[str, Any]:
    canonical_place_id = str(place_id or "").strip()
    item_key_filter = _item_key(item)

    with _STORE_LOCK:
        store = _load_store()
        aggregates = store.get("aggregates") if isinstance(store.get("aggregates"), dict) else {}
        events = store.get("events") if isinstance(store.get("events"), list) else []

        rows: List[Dict[str, Any]] = []
        for entry in aggregates.values():
            if not isinstance(entry, dict):
                continue
            if canonical_place_id and str(entry.get("place_id") or "") != canonical_place_id:
                continue
            if str(item or "").strip() and str(entry.get("item_key") or "") != item_key_filter:
                continue
            rows.append(dict(entry))

        rows.sort(
            key=lambda r: (
                float(_safe_float(r.get("success_score"), 0.0) or 0.0),
                int(_safe_float(r.get("events_count"), 0) or 0),
            ),
            reverse=True,
        )

        return {
            "summary_count": len(rows),
            "rows": rows,
            "events_total": len(events),
            "feedback_version": RECOMMENDATION_FEEDBACK_VERSION,
        }


def get_place_item_feedback_signal(place_id: Any, item: Any = "") -> Dict[str, Any]:
    canonical_place_id = str(place_id or "").strip()
    if not canonical_place_id:
        return {
            "events_count": 0,
            "selection_rate": 0.0,
            "follow_rate": 0.0,
            "scan_after_selection_rate": 0.0,
            "success_score": 0.0,
            "signal_confidence": 0.0,
            "score_adjustment": 0.0,
            "user_feedback_events_count": 0,
            "availability_confidence": 0.0,
            "order_confirmation_rate": 0.0,
            "sauce_default_confidence": 0.0,
            "portion_reliability": 0.0,
            "user_feedback_confidence_source": "none",
        }

    wanted_item_key = _item_key(item)

    with _STORE_LOCK:
        store = _load_store()
        aggregates = store.get("aggregates") if isinstance(store.get("aggregates"), dict) else {}

        item_signal = aggregates.get(_aggregate_key(canonical_place_id, item))
        place_signal = aggregates.get(_aggregate_key(canonical_place_id, ""))

        item_events_n = int(_safe_float(item_signal.get("events_count"), 0) or 0) if isinstance(item_signal, dict) else 0
        item_feedback_n = int(
            _safe_float(item_signal.get("user_feedback_events_count"), 0) or 0
        ) if isinstance(item_signal, dict) else 0

        if isinstance(item_signal, dict) and (item_events_n >= 2 or item_feedback_n >= 2):
            out = dict(item_signal)
            out["signal_source"] = "place_item"
            out.setdefault("user_feedback_events_count", 0)
            out.setdefault("availability_confidence", 0.0)
            out.setdefault("order_confirmation_rate", 0.0)
            out.setdefault("sauce_default_confidence", 0.0)
            out.setdefault("portion_reliability", 0.0)
            out.setdefault("user_feedback_confidence_source", "none")
            return out

        if isinstance(place_signal, dict):
            out = dict(place_signal)
            out["signal_source"] = "place_level"
            out["item"] = _normalize_item_name(item)
            out["item_key"] = wanted_item_key
            out.setdefault("user_feedback_events_count", 0)
            out.setdefault("availability_confidence", 0.0)
            out.setdefault("order_confirmation_rate", 0.0)
            out.setdefault("sauce_default_confidence", 0.0)
            out.setdefault("portion_reliability", 0.0)
            out.setdefault("user_feedback_confidence_source", "none")
            return out

    return {
        "place_id": canonical_place_id,
        "item": _normalize_item_name(item),
        "item_key": wanted_item_key,
        "events_count": 0,
        "selection_rate": 0.0,
        "follow_rate": 0.0,
        "scan_after_selection_rate": 0.0,
        "success_score": 0.0,
        "signal_confidence": 0.0,
        "score_adjustment": 0.0,
        "user_feedback_events_count": 0,
        "availability_confidence": 0.0,
        "order_confirmation_rate": 0.0,
        "sauce_default_confidence": 0.0,
        "portion_reliability": 0.0,
        "user_feedback_confidence_source": "none",
        "signal_source": "none",
    }
