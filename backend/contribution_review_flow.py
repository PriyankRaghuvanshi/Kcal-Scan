"""
Contribution review flow: human-in-the-loop approval of user venue contributions.
Approved contributions safely update local venue profiles/templates/swaps.
No LLM. No auto-merge.
"""
from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from user_venue_contributions import (
    get_contribution,
    list_pending,
    update_contribution_status,
    count_by_place,
    STATUS_ACCEPTED,
    STATUS_REJECTED,
)
from local_venue_profiles import (
    match_local_profile,
    add_candidate_template,
    add_swap_template,
    update_template_in_profile,
    get_profile_by_place_id,
    get_profile_by_normalized_name,
    _normalize_name,
)
# Action types for approval
ACTION_ACCEPT_AS_NEW_TEMPLATE = "accept_as_new_template"
ACTION_ACCEPT_AS_TEMPLATE_UPDATE = "accept_as_template_update"
ACTION_ACCEPT_AS_SWAP = "accept_as_swap"
ACTION_ACCEPT_AS_NOTE_ONLY = "accept_as_note_only"
ACTION_ACCEPT_MARK_INACCURATE_PREVIOUS = "accept_mark_inaccurate_previous"
ACTION_REJECT = "reject"

REVIEW_ACTIONS = (
    ACTION_ACCEPT_AS_NEW_TEMPLATE,
    ACTION_ACCEPT_AS_TEMPLATE_UPDATE,
    ACTION_ACCEPT_AS_SWAP,
    ACTION_ACCEPT_AS_NOTE_ONLY,
    ACTION_ACCEPT_MARK_INACCURATE_PREVIOUS,
    ACTION_REJECT,
)

_AUDIT_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_path() -> Path:
    override = str(os.getenv("CONTRIBUTION_REVIEW_AUDIT_PATH", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "contribution_review_audit.json"


def _load_audit() -> Dict[str, Any]:
    path = _audit_path()
    if not path.exists():
        return {"version": "v1", "reviews": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("reviews", [])
            return data
    except Exception:
        pass
    return {"version": "v1", "reviews": []}


def _save_audit(data: Dict[str, Any]) -> None:
    path = _audit_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _append_review_audit(
    review_id: str,
    contribution_id: str,
    place_id: str,
    reviewer_id: str,
    action_type: str,
    applied_changes: Dict[str, Any],
) -> None:
    with _AUDIT_LOCK:
        data = _load_audit()
        reviews = data.get("reviews") or []
        reviews.append({
            "review_id": review_id,
            "contribution_id": contribution_id,
            "place_id": place_id,
            "reviewer_id": reviewer_id,
            "action_type": action_type,
            "applied_changes": applied_changes,
            "created_at": _now_iso(),
        })
        if len(reviews) > 5000:
            reviews = reviews[-5000:]
        data["reviews"] = reviews
        _save_audit(data)


def list_pending_contributions(
    area_key: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """List pending contributions for review. Optionally filter by area_key."""
    return list_pending(area_key=area_key, limit=limit)


def get_contribution_review_bundle(contribution_id: str) -> Dict[str, Any]:
    """
    Return a review bundle for a contribution: contribution + profile context +
    existing templates/swaps + related contributions.
    """
    c = get_contribution(contribution_id)
    if not c:
        return {"error": "contribution_not_found", "contribution_id": contribution_id}

    place_id = str(c.get("place_id") or "").strip()
    place_name = str(c.get("place_name") or "").strip()
    area_key = str(c.get("area_key") or "").strip()

    profile = None
    if place_id:
        profile = get_profile_by_place_id(place_id)
    if not profile and place_name and area_key:
        profile = get_profile_by_normalized_name(place_name, area_key)

    existing_templates = []
    existing_swaps = []
    if profile:
        existing_templates = list(profile.get("candidate_templates") or [])
        existing_swaps = list(profile.get("swap_templates") or [])

    total_contrib, pending_contrib = count_by_place(place_id, place_name, area_key)

    related = []
    all_pending = list_pending(area_key=area_key, limit=100)
    for r in all_pending:
        if r.get("contribution_id") == contribution_id:
            continue
        rpid = str(r.get("place_id") or "").strip()
        rname = str(r.get("place_name") or "").strip().lower()
        rarea = str(r.get("area_key") or "").strip().lower()
        if (rpid == place_id) or (rname == place_name.lower() and rarea == area_key):
            related.append(r)

    return {
        "contribution": c,
        "place_id": place_id,
        "place_name": place_name,
        "area_key": area_key,
        "existing_profile": profile,
        "existing_candidate_templates": existing_templates,
        "existing_swap_templates": existing_swaps,
        "recent_related_contributions": related[:10],
        "specificity_tier": str(profile.get("specificity_tier") or "") if profile else "",
        "profile_source": str(profile.get("profile_source") or "") if profile else "",
        "contribution_count_for_place": total_contrib,
        "pending_count_for_place": pending_contrib,
    }


def _ensure_diet_tags(
    template: Dict[str, Any],
    contribution_type: str,
) -> Dict[str, Any]:
    """Ensure diet-safe tags on template for veg/vegan contributions."""
    out = dict(template)
    ctype = str(contribution_type or "").strip().lower()
    if ctype == "vegetarian_option_missing":
        out.setdefault("diet_tags", []).append("vegetarian")
        out["vegetarian_possible"] = True
        out.setdefault("food_quality_tags", [])
        if "vegetarian" not in out["food_quality_tags"]:
            out["food_quality_tags"].append("vegetarian")
    elif ctype == "vegan_option_missing":
        out.setdefault("diet_tags", []).append("vegan")
        out["vegan_possible"] = True
        out["vegetarian_possible"] = True
        out.setdefault("food_quality_tags", [])
        for t in ("vegan", "vegetarian"):
            if t not in out["food_quality_tags"]:
                out["food_quality_tags"].append(t)
    return out


def approve_contribution(
    contribution_id: str,
    reviewer_id: str = "",
    action_payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Approve a contribution and apply changes to local venue profile.
    action_payload must include action_type and any template_payload/swap_payload/etc.
    Returns {outcome, applied_changes, error?}.
    """
    action_payload = action_payload or {}
    action_type = str(action_payload.get("action_type") or "").strip()

    if action_type not in REVIEW_ACTIONS or action_type == ACTION_REJECT:
        return {"outcome": "error", "error": "use reject_contribution for reject"}

    c = get_contribution(contribution_id)
    if not c:
        return {"outcome": "error", "error": "contribution_not_found"}

    status = str(c.get("status") or "").strip()
    if status != "pending":
        return {"outcome": "skipped", "reason": f"already_{status}"}

    place_id = str(c.get("place_id") or "").strip()
    place_name = str(c.get("place_name") or "").strip()
    area_key = str(c.get("area_key") or "").strip()
    contribution_type = str(c.get("contribution_type") or "").strip()

    applied = {}

    if action_type == ACTION_ACCEPT_AS_NEW_TEMPLATE:
        tp = action_payload.get("template_payload") or {}
        if not tp.get("template_name") and not tp.get("template_key"):
            sugg = (c.get("payload") or {}).get("suggested_order") or (c.get("payload") or {}).get("item_name")
            if sugg:
                tp = dict(tp)
                tp.setdefault("template_name", str(sugg))
        tp = _ensure_diet_tags(tp, contribution_type)
        ok = add_candidate_template(
            place_id, place_name, area_key, tp,
            profile_source="cached_user_feedback",
        )
        applied["add_template"] = ok
        if ok:
            applied["template_key"] = tp.get("template_key") or ""

    elif action_type == ACTION_ACCEPT_AS_SWAP:
        sp = action_payload.get("swap_payload") or action_payload.get("template_payload") or {}
        ok = add_swap_template(place_id, place_name, area_key, sp)
        applied["add_swap"] = ok

    elif action_type == ACTION_ACCEPT_AS_TEMPLATE_UPDATE:
        tp = action_payload.get("template_payload") or {}
        template_key = str(tp.get("template_key") or "").strip()
        if not template_key:
            return {"outcome": "error", "error": "template_key required for template_update"}
        updates = {
            k: v for k, v in tp.items()
            if k in ("inactive", "confidence", "notes", "negative_flags", "cut_friendly")
        }
        ok = update_template_in_profile(place_id, place_name, area_key, template_key, updates)
        applied["template_update"] = ok

    elif action_type == ACTION_ACCEPT_MARK_INACCURATE_PREVIOUS:
        tp = action_payload.get("template_payload") or c.get("payload") or {}
        template_key = str(tp.get("template_key") or tp.get("item_key") or "").strip()
        if template_key:
            ok = update_template_in_profile(
                place_id, place_name, area_key, template_key,
                {"inactive": True, "notes": str(tp.get("notes") or "marked inaccurate by reviewer")[:200]},
            )
            applied["mark_inactive"] = ok
        else:
            applied["mark_inactive"] = False

    elif action_type == ACTION_ACCEPT_AS_NOTE_ONLY:
        applied["note_only"] = True

    review_id = str(uuid.uuid4())
    reviewer = str(reviewer_id or "").strip()
    notes = str(action_payload.get("reviewer_notes") or "").strip()

    update_contribution_status(
        contribution_id,
        STATUS_ACCEPTED,
        reviewer_id=reviewer,
        reviewer_notes=notes,
        action_applied=applied,
    )

    _append_review_audit(
        review_id, contribution_id, place_id, reviewer, action_type, applied,
    )

    return {
        "outcome": "accepted",
        "review_id": review_id,
        "contribution_id": contribution_id,
        "action_type": action_type,
        "applied_changes": applied,
        "reviewer_id": reviewer,
    }


def reject_contribution(
    contribution_id: str,
    reviewer_id: str = "",
    reviewer_notes: Optional[str] = None,
) -> Dict[str, Any]:
    """Reject a contribution. Status updated only; no profile changes."""
    c = get_contribution(contribution_id)
    if not c:
        return {"outcome": "error", "error": "contribution_not_found"}

    status = str(c.get("status") or "").strip()
    if status != "pending":
        return {"outcome": "skipped", "reason": f"already_{status}"}

    reviewer = str(reviewer_id or "").strip()
    notes = str(reviewer_notes or "").strip()

    update_contribution_status(
        contribution_id,
        STATUS_REJECTED,
        reviewer_id=reviewer,
        reviewer_notes=notes,
    )

    review_id = str(uuid.uuid4())
    _append_review_audit(
        review_id, contribution_id, str(c.get("place_id") or ""), reviewer, ACTION_REJECT, {},
    )

    return {
        "outcome": "rejected",
        "review_id": review_id,
        "contribution_id": contribution_id,
        "reviewer_id": reviewer,
    }
