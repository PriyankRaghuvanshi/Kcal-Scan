"""
Admin ops dashboard aggregator.
Compact internal visibility across:
- enrichment health (post-sync, targets)
- push rollout health
- scan performance health
- Goal Coach funnel (shown → clicked → opened → completed)

Internal tool: no ranking changes, no LLM, no live menu fetch beyond existing health endpoints.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

from suburb_remediation import rank_suburbs_by_worst

# Goal Coach funnel event type groups
_GOAL_COACH_SHOWN_TYPES = {"goal_coach_daily_action_shown", "goal_coach_weekly_action_shown"}
_GOAL_COACH_CLICKED_TYPES = {"goal_coach_daily_action_clicked", "goal_coach_weekly_action_clicked"}
_GOAL_COACH_OPENED_TYPE = "goal_coach_destination_opened"
_GOAL_COACH_COMPLETED_TYPE = "goal_coach_action_completed"
_GOAL_COACH_ACTION_TYPES = (
    "open_healthy_nearby",
    "open_scan_camera",
    "open_supplement_scan",
    "open_daily_summary",
    "open_goal_plan",
)


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


def _goal_coach_norm(v: Any) -> str:
    s = str(v or "").strip().lower()
    return " ".join(s.split()) if s else ""


def summarize_goal_coach_events(events: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregate Goal Coach funnel events into totals, by_source_surface, and by_action_type.
    Events are assumed to be in the same time window.
    """
    totals = {"actions_shown": 0, "actions_clicked": 0, "destinations_opened": 0, "actions_completed": 0}
    by_surface: Dict[str, Dict[str, int]] = {}
    by_action: Dict[str, Dict[str, int]] = {}

    def inc_totals(k: str) -> None:
        if k in totals:
            totals[k] += 1

    def inc_surface(surface: str, k: str) -> None:
        if surface not in by_surface:
            by_surface[surface] = {"shown": 0, "clicked": 0, "opened": 0, "completed": 0}
        key = "shown" if k == "actions_shown" else "clicked" if k == "actions_clicked" else "opened" if k == "destinations_opened" else "completed"
        if key in by_surface[surface]:
            by_surface[surface][key] += 1

    def inc_action(at: str, k: str) -> None:
        at = (at or "").strip().lower()
        if not at or at not in _GOAL_COACH_ACTION_TYPES:
            at = "unknown"
        if at not in by_action:
            by_action[at] = {"shown": 0, "clicked": 0, "opened": 0, "completed": 0}
        key = "shown" if k == "actions_shown" else "clicked" if k == "actions_clicked" else "opened" if k == "destinations_opened" else "completed"
        if key in by_action[at]:
            by_action[at][key] += 1

    for e in events:
        if not isinstance(e, dict):
            continue
        et = _goal_coach_norm(e.get("event_type", ""))
        surface = _goal_coach_norm(e.get("source_surface", "")) or "unknown"
        action_type = _goal_coach_norm(e.get("action_type", ""))

        if et in _GOAL_COACH_SHOWN_TYPES:
            inc_totals("actions_shown")
            inc_surface(surface, "actions_shown")
            inc_action(action_type, "actions_shown")
        elif et in _GOAL_COACH_CLICKED_TYPES:
            inc_totals("actions_clicked")
            inc_surface(surface, "actions_clicked")
            inc_action(action_type, "actions_clicked")
        elif et == _GOAL_COACH_OPENED_TYPE:
            inc_totals("destinations_opened")
            inc_surface(surface, "destinations_opened")
            inc_action(action_type, "destinations_opened")
        elif et == _GOAL_COACH_COMPLETED_TYPE:
            inc_totals("actions_completed")
            if surface not in by_surface:
                by_surface[surface] = {"shown": 0, "clicked": 0, "opened": 0, "completed": 0}
            by_surface[surface]["completed"] = by_surface[surface].get("completed", 0) + 1
            inc_action(action_type, "actions_completed")

    return {
        "totals": totals,
        "by_source_surface": by_surface,
        "by_action_type": by_action,
    }


def _safe_pct(num: int, denom: int, default: float = 0.0) -> float:
    if denom is None or denom <= 0:
        return default
    return round(100.0 * num / denom, 1)


def identify_weakest_goal_coach_path(summary: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deterministically interpret an existing goal_coach funnel summary.
    Returns weakest_action_type, weakest_step, weakest_source_surface, likely_issue_type, recommended_optimization.
    """
    src = summary if isinstance(summary, dict) else {}
    totals = src.get("totals") if isinstance(src.get("totals"), dict) else {}
    rates = src.get("conversion_rates") if isinstance(src.get("conversion_rates"), dict) else {}
    by_surface = src.get("by_source_surface") if isinstance(src.get("by_source_surface"), dict) else {}
    by_action = src.get("by_action_type") if isinstance(src.get("by_action_type"), dict) else {}

    shown = _safe_int(totals.get("actions_shown"), 0)
    clicked = _safe_int(totals.get("actions_clicked"), 0)
    opened = _safe_int(totals.get("destinations_opened"), 0)
    completed = _safe_int(totals.get("actions_completed"), 0)

    # Weakest step: choose the lowest conversion rate among steps with reasonable volume.
    step_rates = {
        "shown_to_clicked": _safe_float(rates.get("shown_to_clicked_pct"), 0.0),
        "clicked_to_opened": _safe_float(rates.get("clicked_to_opened_pct"), 0.0),
        "opened_to_completed": _safe_float(rates.get("opened_to_completed_pct"), 0.0),
    }
    step_denoms = {
        "shown_to_clicked": shown,
        "clicked_to_opened": clicked,
        "opened_to_completed": opened,
    }
    candidate_steps = [k for k, d in step_denoms.items() if d >= 10] or list(step_rates.keys())
    weakest_step = min(candidate_steps, key=lambda k: step_rates.get(k, 0.0))

    # Weakest source surface (by shown->completed) with min shown.
    weakest_surface = "daily_coach"
    best_surface = "daily_coach"
    surf_candidates = []
    for surface, counts in by_surface.items():
        if not isinstance(counts, dict):
            continue
        s = _safe_int(counts.get("shown"), 0)
        c = _safe_int(counts.get("completed"), 0)
        if s >= 10:
            surf_candidates.append((surface, _safe_pct(c, s), s, c))
    if surf_candidates:
        weakest_surface = min(surf_candidates, key=lambda x: (x[1], -x[2]))[0]
        best_surface = max(surf_candidates, key=lambda x: (x[1], x[2]))[0]

    # Weakest action type (by shown->completed) with min shown.
    action_candidates = []
    for action_type, row in by_action.items():
        if not isinstance(row, dict):
            continue
        s = _safe_int(row.get("shown"), 0)
        c = _safe_int(row.get("completed"), 0)
        if s >= 10:
            action_candidates.append((action_type, _safe_pct(c, s), s, c))
    weakest_action_type = min(action_candidates, key=lambda x: (x[1], -x[2]))[0] if action_candidates else "open_scan_camera"
    best_action_type = max(action_candidates, key=lambda x: (x[1], x[2]))[0] if action_candidates else "open_healthy_nearby"

    # Likely issue type from weakest step
    if weakest_step == "shown_to_clicked":
        likely_issue_type = "weak_cta_wording"
        recommended_optimization = "improve_cta_copy_and_reason"
    elif weakest_step == "clicked_to_opened":
        likely_issue_type = "routing_navigation_issue"
        recommended_optimization = "make_destination_open_immediately"
    else:
        likely_issue_type = "destination_friction"
        recommended_optimization = "reduce_destination_completion_friction"

    # Special-case hints by action type
    if weakest_action_type == "open_scan_camera" and weakest_step == "opened_to_completed":
        recommended_optimization = "auto_analyze_after_photo_and_stronger_scan_cta"
    elif weakest_action_type == "open_supplement_scan" and weakest_step in ("shown_to_clicked", "opened_to_completed"):
        recommended_optimization = "clarify_supplement_scan_value_and_steps"
    elif weakest_action_type == "open_healthy_nearby" and weakest_step == "shown_to_clicked":
        recommended_optimization = "strengthen_healthy_nearby_why_copy"

    return {
        "weakest_action_type": weakest_action_type,
        "best_action_type": best_action_type,
        "weakest_step": weakest_step,
        "weakest_source_surface": weakest_surface,
        "best_source_surface": best_surface,
        "likely_issue_type": likely_issue_type,
        "recommended_optimization": recommended_optimization,
        "baseline": {
            "shown": shown,
            "clicked": clicked,
            "opened": opened,
            "completed": completed,
            "shown_to_clicked_pct": step_rates["shown_to_clicked"],
            "clicked_to_opened_pct": step_rates["clicked_to_opened"],
            "opened_to_completed_pct": step_rates["opened_to_completed"],
            "shown_to_completed_pct": _safe_pct(completed, shown),
        },
    }


def get_goal_coach_path_optimization(weakest_hint: Dict[str, Any]) -> Dict[str, Any]:
    """
    Map weakest-path hint to a focused, measurable optimization plan.
    """
    h = weakest_hint if isinstance(weakest_hint, dict) else {}
    action_type = _safe_str(h.get("weakest_action_type"), "open_scan_camera")
    step = _safe_str(h.get("weakest_step"), "opened_to_completed")
    path_key = f"{action_type}:{step}"

    if path_key == "open_scan_camera:opened_to_completed":
        return {
            "path_key": path_key,
            "recommended_copy_change": "Change CTA to be more immediate (e.g. 'Scan your next meal now').",
            "recommended_destination_change": "After taking a meal photo from Goal Coach, auto-start Analyze (best-effort).",
            "recommended_ui_change": "Show a Goal Coach hint in the camera modal explaining auto-analyze + what to do.",
            "measurable_target_step": "opened_to_completed",
            "suggested_target_opened_to_completed_pct": 35.0,
        }
    if path_key == "open_healthy_nearby:shown_to_clicked":
        return {
            "path_key": path_key,
            "recommended_copy_change": "Strengthen daily/weekly CTA wording with a clearer 'why' and expected outcome.",
            "recommended_destination_change": "Ensure preselected filter + banner copy matches coach intent.",
            "recommended_ui_change": "Highlight the top recommended place more clearly as 'best next move'.",
            "measurable_target_step": "shown_to_clicked",
            "suggested_target_shown_to_clicked_pct": 45.0,
        }
    # Default minimal plan
    return {
        "path_key": path_key,
        "recommended_copy_change": "Adjust CTA label/reason to reduce ambiguity.",
        "recommended_destination_change": "Reduce friction in the destination completion step.",
        "recommended_ui_change": "Add a small inline hint so users know how to complete the action.",
        "measurable_target_step": step,
    }


def build_goal_coach_funnel_summary(window_days: int = 7) -> Dict[str, Any]:
    """
    Build compact Goal Coach funnel summary for the ops dashboard.
    Uses list_goal_coach_events for the last window_days; aggregates and computes conversion rates.
    """
    from goal_coach_action_tracking import list_goal_coach_events

    now = datetime.now(timezone.utc)
    start = (now - timedelta(days=max(1, min(30, int(window_days))))).isoformat()[:19]
    end = now.isoformat()[:19]

    events = list_goal_coach_events(start_date=start, end_date=end, limit=10000)
    agg = summarize_goal_coach_events(events)

    totals = agg["totals"]
    shown = totals.get("actions_shown") or 0
    clicked = totals.get("actions_clicked") or 0
    opened = totals.get("destinations_opened") or 0
    completed = totals.get("actions_completed") or 0

    conversion_rates = {
        "shown_to_clicked_pct": _safe_pct(clicked, shown),
        "clicked_to_opened_pct": _safe_pct(opened, clicked),
        "opened_to_completed_pct": _safe_pct(completed, opened),
        "shown_to_completed_pct": _safe_pct(completed, shown),
    }

    by_action_type: Dict[str, Any] = {}
    for action_type, counts in (agg.get("by_action_type") or {}).items():
        s = counts.get("shown") or 0
        c = counts.get("completed") or 0
        by_action_type[action_type] = {
            "shown": counts.get("shown") or 0,
            "clicked": counts.get("clicked") or 0,
            "opened": counts.get("opened") or 0,
            "completed": c,
            "shown_to_completed_pct": _safe_pct(c, s),
        }

    top_action_types = [
        {"action_type": k, "shown_to_completed_pct": v.get("shown_to_completed_pct", 0), "completed": v.get("completed", 0)}
        for k, v in sorted(by_action_type.items(), key=lambda x: (-(x[1].get("completed") or 0), -(x[1].get("shown_to_completed_pct") or 0)))
    ][:5]

    # Largest drop-off step (by absolute loss)
    step_losses = [
        ("shown_to_clicked", shown - clicked),
        ("clicked_to_opened", clicked - opened),
        ("opened_to_completed", opened - completed),
    ]
    largest_dropoff_step = max(step_losses, key=lambda x: x[1])[0] if any(x[1] > 0 for x in step_losses) else "opened_to_completed"
    # Worst action type by shown→completed %
    action_list = [(k, v.get("shown_to_completed_pct") or 0, v.get("shown") or 0) for k, v in by_action_type.items() if (v.get("shown") or 0) >= 1]
    worst_action = min(action_list, key=lambda x: (x[1], -x[2]))[0] if action_list else "open_scan_camera"
    best_action = max(action_list, key=lambda x: (x[1], x[2]))[0] if action_list else "open_healthy_nearby"
    dropoff_summary = {
        "largest_dropoff_step": largest_dropoff_step,
        "largest_dropoff_action_type": worst_action,
        "best_action_type": best_action,
    }

    optimization_hint = identify_weakest_goal_coach_path({
        "totals": totals,
        "conversion_rates": conversion_rates,
        "by_source_surface": agg.get("by_source_surface") or {},
        "by_action_type": by_action_type,
    })
    optimization_plan = get_goal_coach_path_optimization(optimization_hint)

    return {
        "window_days": max(1, min(30, int(window_days))),
        "totals": totals,
        "conversion_rates": conversion_rates,
        "by_source_surface": agg.get("by_source_surface") or {},
        "by_action_type": by_action_type,
        "top_action_types": top_action_types,
        "dropoff_summary": dropoff_summary,
        "optimization_hint": optimization_hint,
        "optimization_plan": optimization_plan,
    }


async def build_ops_dashboard_summary(
    *,
    limit_targets: int = 20,
    limit_areas: int = 5,
    scan_window_days: int = 7,
    goal_coach_window_days: int = 7,
    fetch_fn: Optional[Callable[[float, float], Any]] = None,
) -> Dict[str, Any]:
    enrichment = await build_enrichment_status_summary(
        fetch_fn=fetch_fn,
        limit_targets=limit_targets,
        limit_areas=limit_areas,
    )
    push = build_push_rollout_summary()
    scan = build_scan_health_summary(window_days=scan_window_days)
    goal_coach = build_goal_coach_funnel_summary(window_days=goal_coach_window_days)
    return {
        "generated_at": _now_iso(),
        "enrichment": enrichment,
        "push": push,
        "scan": scan,
        "goal_coach": goal_coach,
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

