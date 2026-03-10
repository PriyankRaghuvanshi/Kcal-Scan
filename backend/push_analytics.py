"""
Push analytics: summarize deliveries, opens, and rollout metrics.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from push_delivery_store import (
    STATUS_DRY_RUN,
    STATUS_RECEIPT_ERROR,
    STATUS_RECEIPT_OK,
    STATUS_SENT,
    STATUS_TICKET_ERROR,
    STATUS_TOKEN_DEACTIVATED,
    list_deliveries,
)

try:
    from meal_decision_event_store import list_meal_decision_events
except ImportError:
    list_meal_decision_events = None  # type: ignore


def _date_range(
    start_date: Optional[str],
    end_date: Optional[str],
) -> tuple:
    """Return (start_iso, end_iso) for filtering. end_date is exclusive."""
    start = start_date or ""
    end = end_date or ""
    return (start, end)


def summarize_push_deliveries(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    dry_run_only: bool = False,
    real_send_only: bool = False,
) -> Dict[str, Any]:
    """Aggregate delivery counts and breakdowns."""
    start, end = _date_range(start_date, end_date)
    deliveries = list_deliveries(
        user_id=user_id,
        alert_type=alert_type,
        start_date=start if start else None,
        end_date=end if end else None,
        dry_run=True if dry_run_only else (False if real_send_only else None),
        limit=5000,
    )

    total_sent = sum(1 for d in deliveries if d.get("status") in (STATUS_SENT, STATUS_RECEIPT_OK))
    total_dry_run = sum(1 for d in deliveries if d.get("dry_run"))
    total_ticket_error = sum(1 for d in deliveries if d.get("status") == STATUS_TICKET_ERROR)
    total_receipt_ok = sum(1 for d in deliveries if d.get("status") == STATUS_RECEIPT_OK)
    total_receipt_error = sum(1 for d in deliveries if d.get("status") == STATUS_RECEIPT_ERROR)
    total_token_deactivated = sum(1 for d in deliveries if d.get("status") == STATUS_TOKEN_DEACTIVATED)

    users = set()
    tokens = set()
    for d in deliveries:
        uid = d.get("user_id")
        if uid:
            users.add(uid)
        tok = d.get("expo_push_token")
        if tok:
            tokens.add(tok)

    by_alert = Counter()
    by_status = Counter()
    by_context = Counter()
    by_place: Counter = Counter()
    for d in deliveries:
        atype = d.get("alert_type") or "unknown"
        by_alert[atype] += 1
        by_status[d.get("status") or "unknown"] += 1
        ctx = (d.get("payload_data") or {}).get("context_mode") or "default"
        by_context[ctx] += 1
        place = d.get("place_name") or d.get("place_id") or "unknown"
        if place and place != "unknown":
            by_place[place] += 1

    top_places = [{"place_name": k, "count": v} for k, v in by_place.most_common(10)]
    top_alert_types = [{"alert_type": k, "count": v} for k, v in by_alert.most_common(10)]

    return {
        "total_deliveries": len(deliveries),
        "total_sent": total_sent,
        "total_dry_run": total_dry_run,
        "total_ticket_error": total_ticket_error,
        "total_receipt_ok": total_receipt_ok,
        "total_receipt_error": total_receipt_error,
        "total_token_deactivated": total_token_deactivated,
        "unique_users_targeted": len(users),
        "unique_tokens_targeted": len(tokens),
        "sent_by_alert_type": dict(by_alert),
        "sent_by_status": dict(by_status),
        "sent_by_context_mode": dict(by_context),
        "top_places_sent": top_places,
        "top_alert_types_sent": top_alert_types,
    }


def summarize_push_opens(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Estimate opens from recommendation_opened events.
    Conservative: matches place_id + user_id within delivery window.
    """
    if not list_meal_decision_events:
        return {
            "total_notification_opens": 0,
            "open_rate_estimate": None,
            "opens_by_alert_type": {},
            "opens_by_place": {},
            "note": "event store unavailable",
        }

    start, end = _date_range(start_date, end_date)
    opens = list_meal_decision_events(
        user_id=user_id or "",
        event_type="recommendation_opened",
        start_date=start if start else None,
        end_date=end if end else None,
        limit=2000,
    )

    deliveries = list_deliveries(
        user_id=user_id,
        alert_type=alert_type,
        start_date=start if start else None,
        end_date=end if end else None,
        dry_run=False,
        limit=5000,
    )
    sent_deliveries = [d for d in deliveries if d.get("status") in (STATUS_SENT, STATUS_RECEIPT_OK)]
    total_sent = len(sent_deliveries)

    by_alert: Counter = Counter()
    by_place: Counter = Counter()
    delivery_by_key: Dict[str, Dict] = {}
    for d in sent_deliveries:
        uid = d.get("user_id") or ""
        pid = d.get("place_id") or ""
        atype = d.get("alert_type") or ""
        created = d.get("created_at") or ""
        key = f"{uid}::{pid}"
        if key not in delivery_by_key or created > (delivery_by_key[key].get("created_at") or ""):
            delivery_by_key[key] = d

    matched_opens = 0
    for o in opens:
        uid = (o.get("user_id") or "").strip()
        pid = (o.get("place_id") or "").strip()
        otime = o.get("created_at") or ""
        key = f"{uid}::{pid}"
        if key in delivery_by_key:
            d = delivery_by_key[key]
            dtime = d.get("created_at") or ""
            if otime >= dtime:
                window_end = ""
                try:
                    dt = datetime.fromisoformat(dtime.replace("Z", "+00:00"))
                    dt_end = dt + timedelta(hours=24)
                    window_end = dt_end.isoformat()
                except Exception:
                    window_end = ""
                if not window_end or otime < window_end:
                    matched_opens += 1
                    atype = d.get("alert_type") or "unknown"
                    by_alert[atype] += 1
                    place = d.get("place_name") or pid or "unknown"
                    by_place[place] += 1

    open_rate = (matched_opens / total_sent) if total_sent else None

    return {
        "total_notification_opens": matched_opens,
        "open_rate_estimate": round(open_rate, 4) if open_rate is not None else None,
        "opens_by_alert_type": dict(by_alert),
        "opens_by_place": dict(by_place),
        "total_opens_from_events": len(opens),
        "note": "open matching is heuristic: place_id+user_id within 24h of delivery",
    }


def build_push_analytics_summary(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    user_id: Optional[str] = None,
    alert_type: Optional[str] = None,
    dry_run_only: bool = False,
    real_send_only: bool = False,
) -> Dict[str, Any]:
    """Combine delivery and open summaries."""
    delivery_summary = summarize_push_deliveries(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        alert_type=alert_type,
        dry_run_only=dry_run_only,
        real_send_only=real_send_only,
    )
    open_summary = summarize_push_opens(
        start_date=start_date,
        end_date=end_date,
        user_id=user_id,
        alert_type=alert_type,
    )
    return {
        "delivery_summary": delivery_summary,
        "open_summary": open_summary,
        "suppressed_due_to_allowlist": None,  # TODO: log when send blocked by allowlist
        "suppressed_due_to_fatigue": None,  # TODO: from candidate suppression_reasons
        "suppressed_due_to_no_tokens": None,  # TODO: log when no tokens
        "suppressed_due_to_duplicate_recent_send": None,  # TODO: log when was_recently_sent
    }
