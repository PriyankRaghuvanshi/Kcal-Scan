"""
Per-user Smart Alert send flow. Used by POST /push/send-smart-alerts and by batch sender.
Callable with (healthy_places_fn, user_id, lat, lng, ...). Keeps push logic in one place.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

# Callable type for healthy_places - avoid circular import
HealthyPlacesFn = Callable[..., Any]


async def send_smart_alert_for_user(
    healthy_places_fn: HealthyPlacesFn,
    user_id: str,
    lat: float,
    lng: float,
    *,
    context: Optional[Dict[str, Any]] = None,
    fatigue: Optional[Dict[str, Any]] = None,
    goal: str = "",
    radius: int = 3000,
    eligible_only: bool = True,
    dry_run: bool = True,
    user_eligibility: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Execute per-user Smart Alert send. Uses existing rollout, duplicate suppression,
    and candidate fallback logic. Returns result dict compatible with single-user endpoint.
    """
    from push_rollout import can_send_real_push, get_push_rollout_mode, get_user_push_eligibility
    from push_token_store import list_tokens_for_user
    from push_delivery_store import create_delivery_record, update_delivery_status, was_recently_sent, get_recently_sent_place_ids
    from expo_push_service import build_expo_push_message, send_expo_push_messages
    from context_modes import infer_context_mode
    from smart_food_alerts import build_smart_food_alert_candidates

    def _safe_float(v: Any, default: float = 0.0) -> float:
        try:
            return float(v)
        except Exception:
            return float(default)

    ctx = context or {}
    fati = fatigue or {}
    cut_mode = (goal or "").strip().lower() in ("cut", "fat_loss")

    remaining_cal = _safe_float(ctx.get("remaining_calories"), 0.0)
    remaining_protein = _safe_float(ctx.get("remaining_protein_g"), 0.0)
    local_hour = int(ctx.get("local_hour") if ctx.get("local_hour") is not None else 12)
    post_workout = bool(ctx.get("post_workout", False))
    late_night = bool(ctx.get("late_night", False))
    poor_sleep = bool(ctx.get("poor_sleep_flag", False))
    high_craving = bool(ctx.get("high_craving_risk_flag", False))
    context_mode_override = (ctx.get("context_mode") or "").strip() or None

    context_info_raw = {
        "remaining_calories": remaining_cal,
        "remaining_protein_g": remaining_protein,
        "post_workout": post_workout,
        "late_night": late_night,
        "poor_sleep_flag": poor_sleep,
        "high_craving_risk_flag": high_craving,
        "context_mode_override": context_mode_override,
        "local_hour": local_hour,
    }
    ctx_modes = infer_context_mode(context_info_raw)
    context_mode = ctx_modes.get("context_mode", "default")

    recent_6h = int(fati.get("recent_alerts_count_6h") if fati.get("recent_alerts_count_6h") is not None else 0)
    recent_24h = int(fati.get("recent_alerts_count_24h") if fati.get("recent_alerts_count_24h") is not None else 0)
    weekly = int(fati.get("weekly_alert_count") if fati.get("weekly_alert_count") is not None else 0)
    ignored = int(fati.get("ignored_streak") if fati.get("ignored_streak") is not None else 0)
    recently_opened = bool(fati.get("recently_opened_app", False))
    recently_viewed = bool(fati.get("recently_viewed_nearby", False))

    payload_hp = await healthy_places_fn(
        lat=lat,
        lng=lng,
        radius=radius,
        cut_mode=cut_mode,
        goal=goal,
        remaining_calories=remaining_cal,
        remaining_protein_g=remaining_protein,
        sort_mode="flat_score",
        user_id=user_id,
        context_mode=context_mode,
        post_workout=post_workout,
        late_night=late_night,
        local_hour=local_hour,
        poor_sleep_flag=poor_sleep,
        high_craving_risk_flag=high_craving,
        limit=12,
    )
    items = payload_hp.get("items") or payload_hp.get("places") or []
    if not isinstance(items, list):
        items = []

    recent_sent_place_ids = get_recently_sent_place_ids(user_id, within_hours=24.0)
    tone_preference = (context or {}).get("tone_preference") or "supportive"
    user_context = {
        "remaining_calories": remaining_cal,
        "remaining_protein_g": remaining_protein,
        "post_workout": post_workout,
        "late_night": late_night,
        "local_hour": local_hour,
        "context_mode": context_mode,
        "poor_sleep_flag": poor_sleep,
        "high_craving_risk_flag": high_craving,
        "recent_alerts_count_6h": recent_6h,
        "recent_alerts_count_24h": recent_24h,
        "weekly_alert_count": weekly,
        "ignored_streak": ignored,
        "recently_opened_app": recently_opened,
        "recently_viewed_nearby": recently_viewed,
        "recent_sent_place_ids_24h": recent_sent_place_ids,
        "tone_preference": tone_preference,
    }
    candidates = build_smart_food_alert_candidates(user_context, items, eligible_only=eligible_only)
    eligible = [c for c in candidates if c.get("eligible_to_send") and c.get("confidence_label") not in ("", "Needs menu check")]

    elig = user_eligibility if user_eligibility is not None else get_user_push_eligibility(user_id)
    allowed, reason = can_send_real_push(user_id, dry_run=dry_run, user_activity=elig)
    rollout_mode = get_push_rollout_mode()
    effective_dry_run = dry_run or not allowed

    tokens = list_tokens_for_user(user_id, active_only=True)
    if not tokens:
        return {
            "ok": True,
            "dry_run": dry_run,
            "real_send_allowed": allowed,
            "real_send_reason": reason,
            "rollout_mode": rollout_mode,
            "user_active_eligible": elig.get("active"),
            "percentage_bucket": elig.get("percentage_bucket"),
            "percentage_allowed": elig.get("percentage_allowed"),
            "candidates_considered": len(candidates),
            "eligible_count": len(eligible),
            "notifications_attempted": 0,
            "tickets_received": 0,
            "candidates_skipped_as_duplicate": 0,
            "candidate_sent_rank": 0,
            "suppressed_reasons": "no_tokens",
            "final_suppressed_reason": "no_tokens",
        }

    top_candidate = None
    candidates_skipped_as_duplicate = 0
    candidate_sent_rank = 0
    final_suppressed_reason: Optional[str] = None
    active_tokens = [t for t in tokens if (t.get("expo_push_token") or "").startswith("ExponentPushToken[")]

    for rank_idx, cand in enumerate(eligible):
        alert_id = f"{cand.get('alert_type')}::{cand.get('place_id')}::{cand.get('best_item_name')}"
        unsuppressed_count = sum(1 for t in active_tokens if not was_recently_sent(user_id, t.get("expo_push_token") or "", alert_id))
        if unsuppressed_count == 0:
            candidates_skipped_as_duplicate += 1
            final_suppressed_reason = "duplicate_recently_sent"
            continue
        top_candidate = cand
        candidate_sent_rank = rank_idx + 1
        break

    if not top_candidate:
        return {
            "ok": True,
            "dry_run": dry_run,
            "real_send_allowed": allowed,
            "real_send_reason": reason,
            "rollout_mode": rollout_mode,
            "user_active_eligible": elig.get("active"),
            "percentage_bucket": elig.get("percentage_bucket"),
            "percentage_allowed": elig.get("percentage_allowed"),
            "candidates_considered": len(candidates),
            "eligible_count": len(eligible),
            "notifications_attempted": 0,
            "tickets_received": 0,
            "candidates_skipped_as_duplicate": candidates_skipped_as_duplicate,
            "candidate_sent_rank": 0,
            "suppressed_reasons": final_suppressed_reason or "no_eligible_candidates",
            "final_suppressed_reason": final_suppressed_reason or "no_eligible_candidates",
        }

    alert_id = f"{top_candidate.get('alert_type')}::{top_candidate.get('place_id')}::{top_candidate.get('best_item_name')}"

    messages = []
    delivery_records = []
    for t in tokens:
        token = t.get("expo_push_token") or ""
        if not token or not token.startswith("ExponentPushToken["):
            continue
        if was_recently_sent(user_id, token, alert_id):
            continue
        msg = build_expo_push_message(top_candidate, token)
        messages.append(msg)
        rec = create_delivery_record(
            user_id=user_id,
            expo_push_token=token,
            alert_id=alert_id,
            alert_type=str(top_candidate.get("alert_type") or ""),
            place_id=str(top_candidate.get("place_id") or ""),
            place_name=str(top_candidate.get("place_name") or ""),
            best_item_name=str(top_candidate.get("best_item_name") or ""),
            title=str(top_candidate.get("title") or ""),
            body=str(top_candidate.get("body") or ""),
            payload_data=msg.get("data"),
            dry_run=effective_dry_run,
        )
        delivery_records.append(rec)

    if not messages:
        return {
            "ok": True,
            "dry_run": dry_run,
            "real_send_allowed": allowed,
            "real_send_reason": reason,
            "rollout_mode": rollout_mode,
            "user_active_eligible": elig.get("active"),
            "percentage_bucket": elig.get("percentage_bucket"),
            "percentage_allowed": elig.get("percentage_allowed"),
            "candidates_considered": len(candidates),
            "eligible_count": len(eligible),
            "notifications_attempted": 0,
            "tickets_received": 0,
            "candidates_skipped_as_duplicate": candidates_skipped_as_duplicate + 1,
            "candidate_sent_rank": 0,
            "suppressed_reasons": "duplicate_recently_sent",
            "final_suppressed_reason": "duplicate_recently_sent",
        }

    result = send_expo_push_messages(messages, dry_run=effective_dry_run)
    tickets = result.get("tickets") or []
    if not effective_dry_run:
        for i, ticket in enumerate(tickets):
            if i >= len(delivery_records):
                break
            rec = delivery_records[i]
            if ticket.get("status") == "ok":
                tid = ticket.get("id")
                update_delivery_status(rec["delivery_id"], status="sent", expo_ticket_id=tid)
            else:
                err_msg = ticket.get("message") or "unknown"
                err_details = ticket.get("details") or {}
                err_code = err_details.get("error") if isinstance(err_details, dict) else None
                update_delivery_status(
                    rec["delivery_id"],
                    status="ticket_error",
                    error_code=str(err_code) if err_code else None,
                    error_message=err_msg[:500],
                )

    return {
        "ok": result.get("ok", True),
        "dry_run": dry_run,
        "real_send_allowed": allowed,
        "real_send_reason": reason,
        "rollout_mode": rollout_mode,
        "user_active_eligible": elig.get("active"),
        "percentage_bucket": elig.get("percentage_bucket"),
        "percentage_allowed": elig.get("percentage_allowed"),
        "candidates_considered": len(candidates),
        "eligible_count": len(eligible),
        "candidates_skipped_as_duplicate": candidates_skipped_as_duplicate,
        "candidate_sent_rank": candidate_sent_rank,
        "notifications_attempted": len(messages),
        "tickets_received": result.get("sent_count", 0),
        "ticket_errors": result.get("error_count", 0),
        "final_suppressed_reason": None,
        "alert_type": str(top_candidate.get("alert_type") or ""),
        "place_name": str(top_candidate.get("place_name") or ""),
        "place_id": str(top_candidate.get("place_id") or ""),
    }
