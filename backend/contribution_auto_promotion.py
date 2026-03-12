"""
Evidence-based auto-promotion pipeline for user venue contributions.

Trust layers:
A. Raw contributions – all submissions stored immediately, not trusted for live ranking
B. Aggregated evidence – per place + normalized suggestion + diet context + type
C. Trusted local venue profiles – only auto-promoted or explicitly approved; used by live ranking

No LLM. No blind auto-accept. Deterministic evidence thresholds.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from local_venue_profiles import (
    add_candidate_template,
    add_swap_template,
    update_template_in_profile,
    get_profile_by_place_id,
    get_profile_by_normalized_name,
    _normalize_name,
    _profile_matches,
    _all_profiles_raw,
    _save_profiles,
)
# Contribution types that can be auto-promoted
PROMOTABLE_TYPES = (
    "better_order_suggestion",
    "vegetarian_option_missing",
    "vegan_option_missing",
    "recommendation_accurate",
    "menu_item_correction",
)

# Generic / vague suggestion tokens – block promotion
GENERIC_TOKENS = (
    "healthy option",
    "protein bowl",
    "lighter menu",
    "lighter option",
    "balanced meal",
    "best menu item",
    "recommended item",
    "smart choice",
    "needs menu check",
)

# Vegan-unsafe tokens – block vegan auto-promotion
VEGAN_UNSAFE_TOKENS = ("dairy", "cheese", "egg", "eggs", "whey", "milk", "butter", "chicken", "meat", "fish", "honey")

# Vegetarian-unsafe tokens – block veg auto-promotion
VEG_UNSAFE_TOKENS = ("chicken", "meat", "fish", "beef", "pork", "lamb", "bacon")

# Promotion audit action types
ACTION_AUTO_PROMOTED_NEW_TEMPLATE = "auto_promoted_new_template"
ACTION_AUTO_PROMOTED_CONFIDENCE_BOOST = "auto_promoted_confidence_boost"
ACTION_AUTO_PROMOTED_NEW_SWAP = "auto_promoted_new_swap"
ACTION_PROMOTION_BLOCKED_CONFLICT = "promotion_blocked_conflict"
ACTION_PROMOTION_BLOCKED_DIET_RISK = "promotion_blocked_diet_risk"
ACTION_PROMOTION_BLOCKED_LOW_EVIDENCE = "promotion_blocked_low_evidence"

# Enrichment queue priority reasons (used when enqueueing near-threshold groups)
REASON_USER_CORRECTION_HIGH_SIGNAL = "user_correction_high_signal"
REASON_VEGAN_OPTION_REPEATED = "vegan_option_repeated"
REASON_VEGETARIAN_OPTION_REPEATED = "vegetarian_option_repeated"
REASON_BETTER_ORDER_REPEATED = "better_order_repeated"
REASON_CONFLICT_NEEDS_REVIEW = "conflict_needs_review"

PROMOTION_THRESHOLD = int(os.getenv("CONTRIBUTION_PROMOTION_THRESHOLD", "8"))
MIN_UNIQUE_USERS = 2
MIN_TOTAL_SUBMISSIONS = 3
RECENT_DAYS = 30

_AUDIT_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _audit_path() -> Path:
    override = str(os.getenv("CONTRIBUTION_AUTO_PROMOTION_AUDIT_PATH", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "contribution_auto_promotion_audit.json"


def _load_all_contributions() -> List[Dict[str, Any]]:
    """Load all contributions (pending and reviewed). For aggregation."""
    from user_venue_contributions import list_all_contributions
    return list_all_contributions(limit=10000)


def _normalize_suggestion(text: str) -> str:
    """Normalize suggestion for grouping. Lowercase, collapse whitespace, strip."""
    if not text or not isinstance(text, str):
        return ""
    s = re.sub(r"\s+", " ", str(text).strip().lower())
    return re.sub(r"[^\w\s\-]", "", s).strip()


def normalize_contribution_signature(contribution: Dict[str, Any]) -> str:
    """
    Build stable signature for grouping: place + type + normalized_suggestion + diet_context.
    """
    place_id = str(contribution.get("place_id") or "").strip()
    place_name = str(contribution.get("place_name") or "").strip().lower()
    area_key = str(contribution.get("area_key") or "").strip().lower()
    ctype = str(contribution.get("contribution_type") or "").strip().lower()
    payload = contribution.get("payload") or {}
    sugg = (
        payload.get("suggested_order")
        or payload.get("item_name")
        or payload.get("suggested_item")
        or payload.get("confirmed_item")
        or ""
    )
    normalized_sugg = _normalize_suggestion(sugg)
    diet = str(payload.get("diet_context") or "").strip().lower()
    if not diet and ctype == "vegetarian_option_missing":
        diet = "vegetarian"
    if not diet and ctype == "vegan_option_missing":
        diet = "vegan"

    place_key = place_id if place_id else f"{place_name}::{area_key}"
    parts = [place_key, ctype, normalized_sugg or "_", diet or "_"]
    raw = "::".join(parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def aggregate_contributions_for_place(
    place_id: Optional[str] = None,
    place_name: Optional[str] = None,
    area_key: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Aggregate contributions by signature for a place (or all if no filters).
    Returns list of aggregate dicts with evidence fields.
    """
    all_contrib = _load_all_contributions()
    pid = str(place_id or "").strip()
    pname = str(place_name or "").strip().lower()
    area = str(area_key or "").strip().lower()

    def _matches(c: Dict[str, Any]) -> bool:
        if not pid and not pname:
            return True
        cpid = str(c.get("place_id") or "").strip()
        cname = str(c.get("place_name") or "").strip().lower()
        carea = str(c.get("area_key") or "").strip().lower()
        if pid and cpid == pid:
            return True
        if pname and area and cname == pname and carea == area:
            return True
        return False

    filtered = [c for c in all_contrib if _matches(c)]
    groups: Dict[str, Dict[str, Any]] = {}

    for c in filtered:
        sig = normalize_contribution_signature(c)
        if sig not in groups:
            payload = c.get("payload") or {}
            sugg = (
                payload.get("suggested_order")
                or payload.get("item_name")
                or payload.get("suggested_item")
                or ""
            )
            diet = str(payload.get("diet_context") or "").strip().lower()
            ctype = str(c.get("contribution_type") or "").strip().lower()
            if not diet and ctype == "vegetarian_option_missing":
                diet = "vegetarian"
            if not diet and ctype == "vegan_option_missing":
                diet = "vegan"

            groups[sig] = {
                "aggregate_signature": sig,
                "place_id": str(c.get("place_id") or "").strip(),
                "place_name": str(c.get("place_name") or "").strip(),
                "area_key": str(c.get("area_key") or "").strip().lower(),
                "contribution_type": ctype,
                "normalized_suggestion": _normalize_suggestion(sugg),
                "diet_context": diet or "",
                "contribution_ids": [],
                "user_ids": [],
                "total_submission_count": 0,
                "unique_user_count": 0,
                "recent_submission_count": 0,
                "recommendation_accurate_count": 0,
                "recommendation_inaccurate_count": 0,
                "chosen_count": 0,
                "helpful_count": 0,
                "conflict_count": 0,
                "veg_conflict_count": 0,
                "vegan_conflict_count": 0,
                "item_not_on_menu_count": 0,
                "same_suggestion_repeat_count": 0,
                "supporting_feedback_count": 0,
                "contradictory_feedback_count": 0,
                "last_submitted_at": None,
            }

        g = groups[sig]
        g["contribution_ids"].append(str(c.get("contribution_id") or ""))
        uid = str(c.get("user_id") or "").strip()
        if uid and uid not in g["user_ids"]:
            g["user_ids"].append(uid)
        g["total_submission_count"] += 1

        ctype = str(c.get("contribution_type") or "").strip().lower()
        if ctype == "recommendation_accurate":
            g["recommendation_accurate_count"] += 1
            g["supporting_feedback_count"] += 1
        elif ctype == "recommendation_inaccurate":
            g["recommendation_inaccurate_count"] += 1
            g["contradictory_feedback_count"] += 1
        elif ctype == "item_not_on_menu":
            g["item_not_on_menu_count"] += 1
        else:
            g["same_suggestion_repeat_count"] += 1

        payload = c.get("payload") or {}
        if payload.get("chosen"):
            g["chosen_count"] += 1
        if payload.get("helpful"):
            g["helpful_count"] += 1

        created = c.get("created_at") or ""
        if created:
            g["last_submitted_at"] = created
            try:
                dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                delta = datetime.now(timezone.utc) - dt
                if delta.days <= RECENT_DAYS:
                    g["recent_submission_count"] += 1
            except Exception:
                pass

        # veg/vegan conflict: would need explicit contradictory evidence in payload; leave at 0

    for g in groups.values():
        g["unique_user_count"] = len(g["user_ids"])
        g["conflict_count"] = (
            g["contradictory_feedback_count"]
            + g["item_not_on_menu_count"]
            + g["veg_conflict_count"]
            + g["vegan_conflict_count"]
        )

    return list(groups.values())


def score_contribution_evidence(aggregate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute promotion_score and reasons.
    promotion_score = positives - negatives (bounded).
    """
    u = int(aggregate.get("unique_user_count") or 0)
    repeat = int(aggregate.get("same_suggestion_repeat_count") or 0)
    support = int(aggregate.get("supporting_feedback_count") or 0)
    chosen = int(aggregate.get("chosen_count") or 0)
    helpful = int(aggregate.get("helpful_count") or 0)
    conflict = int(aggregate.get("conflict_count") or 0)
    contradict = int(aggregate.get("contradictory_feedback_count") or 0)
    not_on_menu = int(aggregate.get("item_not_on_menu_count") or 0)
    veg_conf = int(aggregate.get("veg_conflict_count") or 0)
    vegan_conf = int(aggregate.get("vegan_conflict_count") or 0)

    score = (
        (u * 4)
        + (repeat * 3)
        + (support * 3)
        + (chosen * 3)
        + (helpful * 2)
        - (conflict * 4)
        - (contradict * 4)
        - (not_on_menu * 5)
        - (veg_conf * 5)
        - (vegan_conf * 6)
    )
    score = max(-50, min(100, score))

    positive_reasons: List[str] = []
    if u >= 2:
        positive_reasons.append("multiple_users")
    if repeat >= 2:
        positive_reasons.append("repeated_suggestion")
    if support > 0:
        positive_reasons.append("supporting_feedback")
    if chosen > 0:
        positive_reasons.append("chosen_by_user")
    if helpful > 0:
        positive_reasons.append("marked_helpful")

    blocking_reasons: List[str] = []
    if not_on_menu > 0:
        blocking_reasons.append("item_not_on_menu")
    if veg_conf > 0:
        blocking_reasons.append("vegetarian_conflict")
    if vegan_conf > 0:
        blocking_reasons.append("vegan_conflict")
    if contradict > 0:
        blocking_reasons.append("contradictory_feedback")

    safety_flags: List[str] = []
    diet_ctx = str(aggregate.get("diet_context") or "").strip().lower()
    sugg = str(aggregate.get("normalized_suggestion") or "").strip().lower()
    if diet_ctx == "vegan":
        for t in VEGAN_UNSAFE_TOKENS:
            if t in sugg:
                safety_flags.append("vegan_unsafe_token")
                break
    elif diet_ctx == "vegetarian":
        for t in VEG_UNSAFE_TOKENS:
            if t in sugg:
                safety_flags.append("vegetarian_unsafe_token")
                break

    return {
        "promotion_score": score,
        "positive_reasons": positive_reasons,
        "blocking_reasons": blocking_reasons,
        "safety_flags": safety_flags,
    }


def _is_suggestion_too_generic(normalized_suggestion: str) -> bool:
    if not normalized_suggestion or len(normalized_suggestion) < 4:
        return True
    lower = normalized_suggestion.lower()
    for t in GENERIC_TOKENS:
        if t in lower:
            return True
    return False


def should_auto_promote(aggregate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decide if aggregate can be auto-promoted.
    Returns {promote: bool, action_type?: str, blocked_reason?: str}.
    """
    scored = score_contribution_evidence(aggregate)
    score = scored["promotion_score"]
    blocking = scored["blocking_reasons"]
    safety = scored["safety_flags"]
    positive = scored["positive_reasons"]

    total = int(aggregate.get("total_submission_count") or 0)
    unique = int(aggregate.get("unique_user_count") or 0)
    ctype = str(aggregate.get("contribution_type") or "").strip().lower()
    normalized_sugg = str(aggregate.get("normalized_suggestion") or "").strip()

    if ctype not in PROMOTABLE_TYPES:
        return {"promote": False, "blocked_reason": "contribution_type_not_promotable"}

    if unique < MIN_UNIQUE_USERS and total < MIN_TOTAL_SUBMISSIONS:
        return {"promote": False, "blocked_reason": "insufficient_evidence"}

    if score < PROMOTION_THRESHOLD:
        return {"promote": False, "blocked_reason": "promotion_score_below_threshold"}

    if blocking:
        return {"promote": False, "blocked_reason": "hard_block", "blocking_reasons": blocking}

    if safety:
        return {"promote": False, "blocked_reason": "diet_safety_risk", "safety_flags": safety}

    if _is_suggestion_too_generic(normalized_sugg):
        return {"promote": False, "blocked_reason": "suggestion_too_generic"}

    if ctype == "recommendation_accurate":
        return {"promote": True, "action_type": ACTION_AUTO_PROMOTED_CONFIDENCE_BOOST}

    if ctype in ("vegetarian_option_missing", "vegan_option_missing"):
        return {"promote": True, "action_type": ACTION_AUTO_PROMOTED_NEW_TEMPLATE}

    if ctype == "better_order_suggestion":
        return {"promote": True, "action_type": ACTION_AUTO_PROMOTED_NEW_TEMPLATE}

    if ctype == "menu_item_correction":
        return {"promote": True, "action_type": ACTION_AUTO_PROMOTED_NEW_TEMPLATE}

    return {"promote": True, "action_type": ACTION_AUTO_PROMOTED_NEW_TEMPLATE}


def _append_promotion_audit(record: Dict[str, Any]) -> None:
    import json
    with _AUDIT_LOCK:
        path = _audit_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data: Dict[str, Any] = {"version": "v1", "promotions": []}
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass
        promotions = data.get("promotions") or []
        if not isinstance(promotions, list):
            promotions = []
        promotions.append(record)
        if len(promotions) > 5000:
            promotions = promotions[-5000:]
        data["promotions"] = promotions
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)


def _build_template_from_aggregate(aggregate: Dict[str, Any]) -> Dict[str, Any]:
    """Build candidate template from aggregate for promotion."""
    payload = {}
    for cid in aggregate.get("contribution_ids") or []:
        from user_venue_contributions import get_contribution
        c = get_contribution(cid)
        if c and (c.get("payload") or {}):
            payload = dict(payload)
            payload.update(c.get("payload") or {})

    sugg = (
        payload.get("suggested_order")
        or payload.get("item_name")
        or payload.get("suggested_item")
        or aggregate.get("normalized_suggestion", "")
    )
    template_name = str(sugg).strip() if sugg else ""
    if not template_name:
        return {}

    import re
    template_key = re.sub(r"[^\w]+", "_", template_name.lower())[:64]
    ctype = str(aggregate.get("contribution_type") or "").strip().lower()
    diet_ctx = str(aggregate.get("diet_context") or "").strip().lower()

    template = {
        "template_key": template_key,
        "template_name": template_name,
        "estimated_calories": int(payload.get("estimated_calories") or 520),
        "estimated_protein_g": int(payload.get("estimated_protein_g") or 28),
        "confidence": 0.78,
        "food_quality_tags": list(payload.get("food_quality_tags") or []),
        "cut_friendly": bool(payload.get("cut_friendly", True)),
        "profile_source": "auto_promoted",
        "promoted_from_contribution_ids": aggregate.get("contribution_ids", []),
        "promoted_at": _now_iso(),
        "evidence_score": int(aggregate.get("promotion_score") or 0),
        "support_count": int(aggregate.get("total_submission_count") or 0),
    }
    if diet_ctx:
        template["diet_context"] = diet_ctx
    if ctype == "vegetarian_option_missing" or diet_ctx == "vegetarian":
        template["vegetarian_possible"] = True
        template.setdefault("diet_tags", []).append("vegetarian")
    if ctype == "vegan_option_missing" or diet_ctx == "vegan":
        template["vegan_possible"] = True
        template["vegetarian_possible"] = True
        template.setdefault("diet_tags", []).append("vegan")
    return template


def _find_matching_template(
    profile: Dict[str, Any],
    template_name_normalized: str,
) -> Optional[Dict[str, Any]]:
    """Find existing template with similar name for confidence boost."""
    templates = profile.get("candidate_templates") or []
    for t in templates:
        if isinstance(t, dict) and not t.get("inactive"):
            existing = _normalize_suggestion(str(t.get("template_name") or ""))
            if existing and template_name_normalized and existing == template_name_normalized:
                return t
    return None


def auto_promote_contribution_group(aggregate: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply auto-promotion: add template, boost confidence, or add swap.
    Does NOT destructively overwrite. Marks conflicts for review.
    Returns {ok: bool, action_type: str, applied_changes: dict, error?: str}.
    """
    decision = should_auto_promote(aggregate)
    if not decision.get("promote"):
        blocked = decision.get("blocked_reason", "unknown")
        audit = {
            "promotion_id": str(uuid.uuid4()),
            "place_id": aggregate.get("place_id"),
            "aggregate_signature": aggregate.get("aggregate_signature"),
            "contribution_ids": aggregate.get("contribution_ids", []),
            "action_type": (
                ACTION_PROMOTION_BLOCKED_DIET_RISK
                if "diet" in blocked
                else ACTION_PROMOTION_BLOCKED_CONFLICT
                if "block" in blocked
                else ACTION_PROMOTION_BLOCKED_LOW_EVIDENCE
            ),
            "applied_changes": {},
            "evidence_score": score_contribution_evidence(aggregate).get("promotion_score"),
            "created_at": _now_iso(),
        }
        _append_promotion_audit(audit)
        return {
            "ok": False,
            "action_type": audit["action_type"],
            "applied_changes": {},
            "blocked_reason": blocked,
        }

    action_type = decision.get("action_type") or ACTION_AUTO_PROMOTED_NEW_TEMPLATE
    place_id = str(aggregate.get("place_id") or "").strip()
    place_name = str(aggregate.get("place_name") or "").strip()
    area_key = str(aggregate.get("area_key") or "").strip().lower()
    scored = score_contribution_evidence(aggregate)
    evidence_score = scored["promotion_score"]

    applied: Dict[str, Any] = {}

    if action_type == ACTION_AUTO_PROMOTED_CONFIDENCE_BOOST:
        profile = None
        if place_id:
            profile = get_profile_by_place_id(place_id)
        if not profile and place_name and area_key:
            profile = get_profile_by_normalized_name(place_name, area_key)
        if profile:
            sugg = aggregate.get("normalized_suggestion", "")
            match = _find_matching_template(profile, sugg)
            if match:
                template_key = str(match.get("template_key") or "").strip()
                ok = update_template_in_profile(
                    place_id, place_name, area_key, template_key,
                    {"confidence": 0.85, "notes": f"auto_promoted from {aggregate.get('total_submission_count')} confirmations"},
                )
                applied["confidence_boost"] = ok
                applied["template_key"] = template_key
            else:
                template = _build_template_from_aggregate(aggregate)
                if template:
                    template["profile_source"] = "community_confirmed"
                    template["confidence"] = 0.80
                    ok = add_candidate_template(
                        place_id, place_name, area_key, template,
                        profile_source="auto_promoted",
                    )
                    applied["add_template"] = ok
        else:
            template = _build_template_from_aggregate(aggregate)
            if template:
                template["profile_source"] = "community_confirmed"
                ok = add_candidate_template(
                    place_id, place_name, area_key, template,
                    profile_source="auto_promoted",
                )
                applied["add_template"] = ok

    else:
        template = _build_template_from_aggregate(aggregate)
        if not template:
            return {
                "ok": False,
                "action_type": action_type,
                "applied_changes": {},
                "error": "could_not_build_template",
            }
        profile = None
        if place_id:
            profile = get_profile_by_place_id(place_id)
        if not profile and place_name and area_key:
            profile = get_profile_by_normalized_name(place_name, area_key)
        if profile:
            existing_match = _find_matching_template(profile, aggregate.get("normalized_suggestion", ""))
            if existing_match:
                applied["skipped"] = "existing_template_match"
                applied["conflict_for_review"] = True
                audit = {
                    "promotion_id": str(uuid.uuid4()),
                    "place_id": place_id,
                    "aggregate_signature": aggregate.get("aggregate_signature"),
                    "contribution_ids": aggregate.get("contribution_ids", []),
                    "action_type": ACTION_PROMOTION_BLOCKED_CONFLICT,
                    "applied_changes": applied,
                    "evidence_score": evidence_score,
                    "created_at": _now_iso(),
                }
                _append_promotion_audit(audit)
                return {"ok": False, "action_type": ACTION_PROMOTION_BLOCKED_CONFLICT, "applied_changes": applied}
        ok = add_candidate_template(
            place_id, place_name, area_key, template,
            profile_source="auto_promoted",
        )
        applied["add_template"] = ok
        if template.get("template_key"):
            applied["template_key"] = template["template_key"]

    audit = {
        "promotion_id": str(uuid.uuid4()),
        "place_id": place_id,
        "aggregate_signature": aggregate.get("aggregate_signature"),
        "contribution_ids": aggregate.get("contribution_ids", []),
        "action_type": action_type,
        "applied_changes": applied,
        "evidence_score": evidence_score,
        "created_at": _now_iso(),
    }
    _append_promotion_audit(audit)

    try:
        from supabase_intelligence_store import upsert_trusted_profile_to_supabase
        profile = get_profile_by_place_id(place_id) if place_id else get_profile_by_normalized_name(place_name, area_key)
        if profile:
            upsert_trusted_profile_to_supabase(profile)
    except Exception:
        pass

    return {"ok": True, "action_type": action_type, "applied_changes": applied}


def _enqueue_near_threshold(aggregate: Dict[str, Any], blocked_reason: str) -> None:
    """Enqueue place for enrichment when group is near promotion threshold."""
    place_id = str(aggregate.get("place_id") or "").strip()
    if not place_id:
        return
    ctype = str(aggregate.get("contribution_type") or "").strip().lower()
    try:
        from background_enrichment_queue import enqueue, was_recently_enqueued

        if was_recently_enqueued(place_id, within_hours=24.0):
            return

        if ctype == "vegan_option_missing":
            reason = REASON_VEGAN_OPTION_REPEATED
        elif ctype == "vegetarian_option_missing":
            reason = REASON_VEGETARIAN_OPTION_REPEATED
        elif ctype == "better_order_suggestion":
            reason = REASON_BETTER_ORDER_REPEATED
        elif "conflict" in blocked_reason:
            reason = REASON_CONFLICT_NEEDS_REVIEW
        else:
            reason = REASON_USER_CORRECTION_HIGH_SIGNAL

        enqueue(
            place_id,
            place_name=str(aggregate.get("place_name") or "").strip(),
            reason_enqueued=reason,
        )
    except Exception:
        pass


def _is_near_threshold(aggregate: Dict[str, Any], decision: Dict[str, Any]) -> bool:
    """True if aggregate is close to promotion but blocked."""
    if decision.get("promote"):
        return False
    blocked = decision.get("blocked_reason") or ""
    if blocked in ("insufficient_evidence", "promotion_score_below_threshold"):
        total = int(aggregate.get("total_submission_count") or 0)
        unique = int(aggregate.get("unique_user_count") or 0)
        score = int(aggregate.get("promotion_score") or 0)
        if total >= 2 or unique >= 2 or score >= (PROMOTION_THRESHOLD - 4):
            return True
    return False


def run_auto_promotion_for_place(
    place_id: Optional[str] = None,
    area_key: Optional[str] = None,
    place_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Run auto-promotion for a single place. Returns summary."""
    aggregates = aggregate_contributions_for_place(
        place_id=place_id or None,
        place_name=place_name or None,
        area_key=area_key or None,
    )
    promoted = 0
    blocked = 0
    enqueued = 0
    results: List[Dict[str, Any]] = []
    for agg in aggregates:
        scored = score_contribution_evidence(agg)
        agg["promotion_score"] = scored["promotion_score"]
        agg["positive_reasons"] = scored["positive_reasons"]
        agg["blocking_reasons"] = scored["blocking_reasons"]
        decision = should_auto_promote(agg)
        result = auto_promote_contribution_group(agg)
        results.append({"aggregate_signature": agg["aggregate_signature"], "result": result})
        if result.get("ok"):
            promoted += 1
        else:
            blocked += 1
            blocked_reason = decision.get("blocked_reason") or result.get("blocked_reason") or ""
            if _is_near_threshold(agg, decision):
                _enqueue_near_threshold(agg, blocked_reason)
                enqueued += 1
    return {
        "place_id": place_id,
        "area_key": area_key,
        "aggregates_considered": len(aggregates),
        "promoted": promoted,
        "blocked": blocked,
        "enqueued_for_enrichment": enqueued,
        "results": results,
    }


def run_auto_promotion_all(limit: int = 100) -> Dict[str, Any]:
    """Run auto-promotion across all places with contributions."""
    all_contrib = _load_all_contributions()
    seen_places: Dict[str, Tuple[str, str, str]] = {}
    for c in all_contrib:
        if not isinstance(c, dict):
            continue
        pid = str(c.get("place_id") or "").strip()
        pname = str(c.get("place_name") or "").strip().lower()
        area = str(c.get("area_key") or "").strip().lower()
        key = pid if pid else f"{pname}::{area}"
        if key and key not in seen_places:
            seen_places[key] = (pid or "", pname, area)

    total_promoted = 0
    total_blocked = 0
    total_enqueued = 0
    place_results: List[Dict[str, Any]] = []
    for key, (pid, pname, area) in list(seen_places.items())[:limit]:
        r = run_auto_promotion_for_place(place_id=pid or None, place_name=pname or None, area_key=area or None)
        place_results.append(r)
        total_promoted += r.get("promoted", 0)
        total_blocked += r.get("blocked", 0)
        total_enqueued += r.get("enqueued_for_enrichment", 0)

    return {
        "places_considered": len(place_results),
        "total_promoted": total_promoted,
        "total_blocked": total_blocked,
        "total_enqueued_for_enrichment": total_enqueued,
        "place_results": place_results,
    }


def get_auto_promotion_status(
    place_id: Optional[str] = None,
    area_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Status of aggregates and promotion eligibility for a place."""
    aggregates = aggregate_contributions_for_place(
        place_id=place_id or None,
        area_key=area_key or None,
    )
    statuses: List[Dict[str, Any]] = []
    for agg in aggregates:
        scored = score_contribution_evidence(agg)
        decision = should_auto_promote(agg)
        statuses.append({
            "aggregate_signature": agg.get("aggregate_signature"),
            "contribution_type": agg.get("contribution_type"),
            "normalized_suggestion": agg.get("normalized_suggestion"),
            "total_submission_count": agg.get("total_submission_count"),
            "unique_user_count": agg.get("unique_user_count"),
            "promotion_score": scored["promotion_score"],
            "positive_reasons": scored["positive_reasons"],
            "blocking_reasons": scored["blocking_reasons"],
            "safety_flags": scored["safety_flags"],
            "would_promote": decision.get("promote", False),
            "blocked_reason": decision.get("blocked_reason"),
        })
    return {
        "place_id": place_id,
        "area_key": area_key,
        "aggregates": statuses,
    }
