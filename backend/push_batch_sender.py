"""
Batch Smart Alert sending: iterate eligible users, apply rollout, send at most one per user.
Scheduler-friendly. Respects duplicate suppression, fatigue, rollout mode.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

# Avoid circular import: healthy_places and send_smart_alert_for_user injected at runtime


def _env_int(name: str, default: int, min_val: int = 0, max_val: int = 99999) -> int:
    try:
        v = int(os.getenv(name, str(default)))
        return max(min_val, min(max_val, v))
    except (TypeError, ValueError):
        return default


def _batch_user_limit() -> int:
    return _env_int("PUSH_BATCH_USER_LIMIT", 500, 1, 2000)


def _sample_results_limit() -> int:
    return _env_int("PUSH_BATCH_SAMPLE_RESULTS_LIMIT", 25, 0, 200)


def list_users_with_active_push_tokens(limit: int = 1000) -> List[Dict[str, Any]]:
    """
    Return users with active push tokens for batch consideration.
    Each row: user_id, active_tokens_count, last_seen_at, updated_at.
    """
    from push_token_store import list_users_with_active_push_tokens as _list
    effective = max(1, min(10000, limit))
    return _list(limit=effective)


def get_batch_push_candidates(
    limit_users: int = 1000,
) -> List[Dict[str, Any]]:
    """
    Return batch-eligible user candidates: has active tokens + has stored location.
    Each row: user_id, active_tokens_count, last_seen_at, lat, lng, updated_at.
    """
    from push_token_store import list_users_with_active_push_tokens
    from user_last_location_store import get_user_location

    users = list_users_with_active_push_tokens(limit=limit_users)
    out = []
    for u in users:
        uid = (u.get("user_id") or "").strip()
        if not uid:
            continue
        loc = get_user_location(uid)
        if not loc:
            continue
        lat = loc.get("lat")
        lng = loc.get("lng")
        if lat is None or lng is None:
            continue
        try:
            float(lat)
            float(lng)
        except (TypeError, ValueError):
            continue
        out.append({
            "user_id": uid,
            "active_tokens_count": u.get("active_tokens_count", 0),
            "last_seen_at": u.get("last_seen_at"),
            "updated_at": u.get("updated_at"),
            "lat": float(lat),
            "lng": float(lng),
        })
    return out


def _get_fatigue_context(user_id: str) -> Dict[str, Any]:
    """Build fatigue dict from delivery store for batch (no app context)."""
    from push_delivery_store import list_deliveries

    now = datetime.now(timezone.utc)
    cut_6h = (now - timedelta(hours=6)).isoformat()
    cut_24h = (now - timedelta(hours=24)).isoformat()

    recent = list_deliveries(
        user_id=user_id,
        dry_run=False,
        start_date=cut_24h,
        limit=100,
    )
    sent = [d for d in recent if d.get("status") in ("sent", "receipt_ok", "receipt_error")]
    count_6h = sum(1 for d in sent if (d.get("created_at") or "") >= cut_6h)
    count_24h = len(sent)
    return {
        "recent_alerts_count_6h": count_6h,
        "recent_alerts_count_24h": count_24h,
        "weekly_alert_count": 0,  # Batch has no weekly context; fatigue still enforced
        "ignored_streak": 0,
        "recently_opened_app": False,
        "recently_viewed_nearby": False,
    }


async def send_smart_alerts_for_eligible_users(
    limit_users: int = 1000,
    dry_run: bool = True,
    *,
    healthy_places_fn: Optional[Callable[..., Any]] = None,
    send_smart_alert_fn: Optional[Callable[..., Any]] = None,
) -> Dict[str, Any]:
    """
    Run batch Smart Alert send for eligible users. Scheduler entrypoint.
    Uses conservative defaults: dry_run=True or low limit if called with no args.
    Returns production-debuggable summary with skip_reasons, sample_results.
    """
    from push_rollout import (
        can_send_real_push,
        get_push_rollout_mode,
        get_user_push_eligibility,
    )
    from push_send_flow import send_smart_alert_for_user
    from user_last_location_store import get_user_location

    limit = max(1, min(2000, limit_users or _batch_user_limit()))
    sample_limit = _sample_results_limit()

    if healthy_places_fn is None or send_smart_alert_fn is None:
        # Late import to avoid circular dependency; main must be loaded
        import main as main_mod
        healthy_places_fn = healthy_places_fn or main_mod.healthy_places
        send_smart_alert_fn = send_smart_alert_fn or send_smart_alert_for_user

    users_with_tokens = list_users_with_active_push_tokens(limit=limit)
    users_considered = len(users_with_tokens)

    skip_reasons: Dict[str, int] = {
        "no_tokens": 0,
        "no_location": 0,
        "inactive_user": 0,
        "allowlist_blocked": 0,
        "percentage_blocked": 0,
        "fatigue_limit_6h": 0,
        "fatigue_limit_24h": 0,
        "duplicate_recently_sent": 0,
    }
    alerts_sent = 0
    alerts_suppressed = 0
    receipt_candidates = 0
    sample_results: List[Dict[str, Any]] = []

    for u in users_with_tokens:
        uid = (u.get("user_id") or "").strip()
        if not uid:
            skip_reasons["no_tokens"] = skip_reasons.get("no_tokens", 0) + 1
            continue

        loc = get_user_location(uid)
        if not loc:
            skip_reasons["no_location"] = skip_reasons.get("no_location", 0) + 1
            if len(sample_results) < sample_limit:
                sample_results.append({
                    "user_id": uid,
                    "sent": False,
                    "skipped": True,
                    "final_suppressed_reason": "no_location",
                })
            continue

        lat = loc.get("lat")
        lng = loc.get("lng")
        if lat is None or lng is None:
            skip_reasons["no_location"] = skip_reasons.get("no_location", 0) + 1
            continue

        user_eligibility = get_user_push_eligibility(uid)
        allowed, reason = can_send_real_push(uid, dry_run=dry_run, user_activity=user_eligibility)

        if not allowed and dry_run is False:
            if reason == "inactive_user":
                skip_reasons["inactive_user"] = skip_reasons.get("inactive_user", 0) + 1
            elif reason == "allowlist_blocked":
                skip_reasons["allowlist_blocked"] = skip_reasons.get("allowlist_blocked", 0) + 1
            elif reason == "percentage_blocked":
                skip_reasons["percentage_blocked"] = skip_reasons.get("percentage_blocked", 0) + 1
            elif reason == "fatigue_limit_6h":
                skip_reasons["fatigue_limit_6h"] = skip_reasons.get("fatigue_limit_6h", 0) + 1
            elif reason == "fatigue_limit_24h":
                skip_reasons["fatigue_limit_24h"] = skip_reasons.get("fatigue_limit_24h", 0) + 1
            if len(sample_results) < sample_limit:
                sample_results.append({
                    "user_id": uid,
                    "sent": False,
                    "skipped": True,
                    "final_suppressed_reason": reason,
                })
            continue

        fatigue = _get_fatigue_context(uid)
        result = await send_smart_alert_fn(
            healthy_places_fn,
            uid,
            float(lat),
            float(lng),
            context={},
            fatigue=fatigue,
            eligible_only=True,
            dry_run=dry_run,
            user_eligibility=user_eligibility,
        )

        attempted = result.get("notifications_attempted", 0)
        tickets = result.get("tickets_received", 0)
        final_reason = result.get("final_suppressed_reason") or ""
        cand_sent_rank = result.get("candidate_sent_rank", 0)

        if attempted > 0 and tickets > 0:
            alerts_sent += 1
            receipt_candidates += tickets
            if len(sample_results) < sample_limit:
                sample_results.append({
                    "user_id": uid,
                    "sent": True,
                    "skipped": False,
                    "real_send_reason": result.get("real_send_reason"),
                    "candidate_sent_rank": cand_sent_rank,
                    "alert_type": result.get("alert_type"),
                    "place_name": result.get("place_name"),
                    "final_suppressed_reason": None,
                })
        else:
            alerts_suppressed += 1
            if final_reason == "duplicate_recently_sent":
                skip_reasons["duplicate_recently_sent"] = skip_reasons.get("duplicate_recently_sent", 0) + 1
            if len(sample_results) < sample_limit:
                sample_results.append({
                    "user_id": uid,
                    "sent": False,
                    "skipped": True,
                    "real_send_reason": result.get("real_send_reason"),
                    "final_suppressed_reason": final_reason or "no_eligible_candidates",
                    "candidate_sent_rank": cand_sent_rank,
                    "alert_type": result.get("alert_type"),
                    "place_name": result.get("place_name"),
                })

    users_eligible = alerts_sent + alerts_suppressed
    users_skipped = users_considered - users_eligible

    return {
        "ok": True,
        "dry_run": dry_run,
        "users_considered": users_considered,
        "users_eligible": users_eligible,
        "users_skipped": users_skipped,
        "alerts_sent": alerts_sent,
        "alerts_suppressed": alerts_suppressed,
        "receipt_candidates": receipt_candidates,
        "skip_reasons": skip_reasons,
        "sample_results": sample_results,
        "rollout_mode": get_push_rollout_mode(),
    }
