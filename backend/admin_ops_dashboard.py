"""
Admin ops dashboard aggregator.
Compact internal visibility across:
- enrichment health (post-sync, targets)
- push rollout health
- scan performance health

Internal tool: no ranking changes, no LLM, no live menu fetch beyond existing health endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from suburb_remediation import rank_suburbs_by_worst


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return default


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def _safe_str(v: Any, default: str = "") -> str:
    s = str(v or "").strip() if v is not None else ""
    return s if s else default


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def build_enrichment_status_summary(
    *,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
    limit_targets: int = 20,
    limit_areas: int = 5,
) -> Dict[str, Any]:
    """
    Enrichment summary: post-sync reports + weak suburbs + next targets.
    fetch_fn(lat, lng) should be healthy_places-style response.
    """
    from local_launch_enrichment_pack import list_priority_launch_areas
    from post_sync_remediation_report import (
        run_post_sync_reports_for_priority_areas,
        build_next_enrichment_targets_from_fetch,
    )

    priority_suburbs = list_priority_launch_areas(limit=limit_areas)

    reports_result = await run_post_sync_reports_for_priority_areas(
        fetch_fn=fetch_fn,
        limit_areas=limit_areas,
        include_examples=False,
    )
    reports = reports_result.get("areas") or []

    # Weak suburbs: use same composite as remediation (generic + chain hidden + dup cluster)
    ranked = rank_suburbs_by_worst(reports)
    weak_suburbs = []
    for r in ranked[: max(1, min(10, len(ranked) or 10))]:
        le = r.get("local_enrichment") or {}
        sync = r.get("canonical_sync") or {}
        weak_suburbs.append({
            "area_key": r.get("area_key"),
            "display_name": r.get("display_name") or r.get("area_key"),
            "percent_top_5_generic_fallback": r.get("percent_top_5_generic_fallback"),
            "visible_results_using_local_profiles_percent": le.get("visible_results_using_local_profiles_percent"),
            "known_chain_hidden_rate": r.get("known_chain_hidden_rate"),
            "duplicate_score_cluster_rate_top_5": r.get("duplicate_score_cluster_rate_top_5"),
            "canonical_trusted_local_profiles_count": le.get("canonical_trusted_local_profiles_count")
            or le.get("canonical_trusted_local_profiles_count")
            or sync.get("canonical_profile_count", 0),
            "pack_seeded_profiles": (sync.get("pack_seeded_profiles") or sync.get("local_pack_seeded_count") or 0),
            "auto_promoted_profiles": (sync.get("auto_promoted_profiles") or sync.get("local_auto_promoted_count") or 0),
        })

    # Overview: per-area generic percent
    overview = [
        {
            "area_key": r.get("area_key"),
            "display_name": r.get("display_name") or r.get("area_key"),
            "percent_top_5_generic_fallback": r.get("percent_top_5_generic_fallback"),
        }
        for r in reports
    ]

    targets_result = await build_next_enrichment_targets_from_fetch(
        fetch_fn=fetch_fn,
        limit_total=limit_targets,
        limit_areas=limit_areas,
    )
    next_targets = targets_result.get("targets") or []
    by_action = targets_result.get("by_action") or {}

    return {
        "priority_suburbs": priority_suburbs,
        "weak_suburbs": weak_suburbs,
        "next_targets": next_targets,
        "by_action": by_action,
        "generic_fallback_percent_overview": overview,
        "last_post_sync_run_hint": {
            "computed_at": _now_iso(),
            "samples_per_area": 5,
            "include_examples": False,
        },
    }


def build_push_rollout_summary() -> Dict[str, Any]:
    """
    Push summary: rollout config + batch eligibility estimate + recent delivery counts.
    Does not send notifications.
    """
    from push_rollout import get_rollout_status
    from push_batch_sender import (
        _batch_user_limit,
        _sample_results_limit,
        list_users_with_active_push_tokens,
    )
    from user_last_location_store import list_user_ids_with_location
    from push_delivery_store import list_deliveries

    status = get_rollout_status()
    status["batch_user_limit"] = _batch_user_limit()
    status["batch_sample_results_limit"] = _sample_results_limit()

    users_with_tokens = list_users_with_active_push_tokens(limit=10000)
    users_with_location = set(list_user_ids_with_location(limit=10000))
    batch_eligible_count = sum(1 for u in users_with_tokens if (u.get("user_id") or "").strip() in users_with_location)
    status["users_with_active_tokens"] = len(users_with_tokens)
    status["users_with_stored_location"] = len(users_with_location)
    status["batch_eligible_estimate"] = batch_eligible_count

    # Recent delivery snapshot (last 24h)
    now = datetime.now(timezone.utc)
    start_24h = (now - timedelta(hours=24)).isoformat()
    recent = list_deliveries(start_date=start_24h, limit=5000)
    sent = sum(1 for d in recent if d.get("status") in ("sent", "receipt_ok", "receipt_error"))
    suppressed = sum(1 for d in recent if d.get("status") in ("dry_run", "queued"))
    receipt_ok = sum(1 for d in recent if d.get("status") == "receipt_ok")
    receipt_error = sum(1 for d in recent if d.get("status") == "receipt_error")
    status["recent_sent_count"] = sent
    status["recent_suppressed_count"] = suppressed
    status["recent_receipt_ok_count"] = receipt_ok
    status["recent_receipt_error_count"] = receipt_error

    return status


def build_scan_health_summary(window_days: int = 7) -> Dict[str, Any]:
    from scan_performance_analytics import build_scan_performance_summary
    return build_scan_performance_summary(window_days=window_days)


async def build_ops_dashboard_summary(
    *,
    limit_targets: int = 20,
    limit_areas: int = 5,
    scan_window_days: int = 7,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
) -> Dict[str, Any]:
    enrichment = await build_enrichment_status_summary(
        fetch_fn=fetch_fn,
        limit_targets=limit_targets,
        limit_areas=limit_areas,
    )
    push = build_push_rollout_summary()
    scan = build_scan_health_summary(window_days=scan_window_days)
    return {
        "generated_at": _now_iso(),
        "enrichment": enrichment,
        "push": push,
        "scan": scan,
        "actions": {
            "apply_next_targets_endpoint": "/admin/ops-dashboard/apply-next-targets",
            "batch_push_dry_run_endpoint": "/admin/ops-dashboard/run-batch-dry-run",
            "check_receipts_endpoint": "/admin/ops-dashboard/check-receipts",
            "auto_promote_endpoint": "/admin/ops-dashboard/run-auto-promote",
        },
    }


async def run_apply_next_targets(
    *,
    limit: int = 20,
    area_keys: Optional[List[str]] = None,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
) -> Dict[str, Any]:
    from apply_enrichment_targets import apply_next_enrichment_targets
    return await apply_next_enrichment_targets(limit=limit, area_keys=area_keys, fetch_fn=fetch_fn)


async def run_push_batch_dry_run(
    *,
    limit_users: int = 100,
) -> Dict[str, Any]:
    from push_batch_sender import send_smart_alerts_for_eligible_users
    return await send_smart_alerts_for_eligible_users(limit_users=limit_users, dry_run=True)


async def run_check_receipts(
    *,
    limit: int = 100,
) -> Dict[str, Any]:
    from push_delivery_store import list_pending_receipt_ids
    from expo_push_service import fetch_expo_push_receipts, is_device_not_registered
    from push_delivery_store import (
        get_delivery_by_ticket_id,
        update_delivery_status,
        mark_token_deactivated_for_delivery,
    )

    pending = list_pending_receipt_ids(limit=limit)
    if not pending:
        return {"ok": True, "pending_count": 0, "processed": 0, "receipt_ok": 0, "receipt_error": 0, "tokens_deactivated": 0}

    receipts_result = fetch_expo_push_receipts(pending)
    receipts = receipts_result.get("receipts") or {}
    receipt_ok = 0
    receipt_error = 0
    tokens_deactivated = 0

    for tid, receipt in receipts.items():
        delivery = get_delivery_by_ticket_id(tid)
        if not delivery:
            continue
        if receipt.get("status") == "ok":
            update_delivery_status(delivery["delivery_id"], status="receipt_ok", expo_receipt_id=tid)
            receipt_ok += 1
        else:
            err_details = receipt.get("details") or {}
            err_msg = receipt.get("message") or ""
            update_delivery_status(
                delivery["delivery_id"],
                status="receipt_error",
                expo_receipt_id=tid,
                error_code=str(err_details.get("error") or receipt.get("status") or "error"),
                error_message=str(err_msg or ""),
            )
            receipt_error += 1
            if is_device_not_registered(receipt):
                d2 = mark_token_deactivated_for_delivery(delivery["delivery_id"])
                if d2:
                    tokens_deactivated += 1

    return {
        "ok": receipts_result.get("ok", True),
        "pending_count": len(pending),
        "processed": len(receipts),
        "receipt_ok": receipt_ok,
        "receipt_error": receipt_error,
        "tokens_deactivated": tokens_deactivated,
    }


def run_auto_promote(
    *,
    limit: int = 100,
    area_key: Optional[str] = None,
) -> Dict[str, Any]:
    from contribution_auto_promotion import run_auto_promotion_all, run_auto_promotion_for_place
    if area_key:
        return run_auto_promotion_for_place(area_key=str(area_key).strip(), place_id=None, place_name=None)
    return run_auto_promotion_all(limit=limit)

