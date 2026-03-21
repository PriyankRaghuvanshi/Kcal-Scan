from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from chain_rollout_registry import get_chain_runtime_config, load_chain_rollout_registry


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return int(default)


def _norm_chain_key(v: Any) -> str:
    return _safe_text(v).lower().replace(" ", "_")


def _norm_market(v: Any) -> str:
    token = _safe_text(v).upper()
    return token if token in {"AU", "IN", "US"} else ""


def _source_token(payload: Dict[str, Any]) -> str:
    raw = _safe_text(
        payload.get("menu_item_source")
        or payload.get("menu_source_resolved")
        or payload.get("menu_items_source_resolved")
        or payload.get("menu_source")
    ).lower()
    if raw in {"chain_registry", "ingested_chain_item"}:
        return "chain_registry"
    return raw or "heuristic"


def _specificity_token(payload: Dict[str, Any]) -> str:
    return _safe_text(payload.get("chosen_candidate_specificity_tier")).lower()


def _subject_for_canary(payload: Dict[str, Any]) -> str:
    return _safe_text(payload.get("user_id") or payload.get("uid") or payload.get("place_id") or payload.get("id"))


def _is_in_allowlist(settings: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    user_id = _safe_text(payload.get("user_id") or payload.get("uid"))
    region = _safe_text(payload.get("market") or payload.get("country_code")).upper()
    users = {str(x).strip() for x in (settings.get("verified_tag_allowlist_user_ids") or []) if str(x).strip()}
    regions = {str(x).strip().upper() for x in (settings.get("verified_tag_allowlist_regions") or []) if str(x).strip()}
    return bool((user_id and user_id in users) or (region and region in regions))


def _is_in_canary(settings: Dict[str, Any], payload: Dict[str, Any]) -> bool:
    if _is_in_allowlist(settings, payload):
        return True
    pct = max(0, min(100, _safe_int(settings.get("verified_tag_canary_percent"), 0)))
    if pct >= 100:
        return True
    if pct <= 0:
        return False
    subject = _subject_for_canary(payload)
    if not subject:
        return False
    digest = hashlib.sha256(subject.encode("utf-8")).hexdigest()
    bucket = int(digest[:8], 16) % 100
    return bucket < pct


def _source_age_days(payload: Dict[str, Any]) -> Optional[int]:
    stamp = _safe_text(payload.get("last_ingested_at") or payload.get("source_updated_at"))
    if not stamp:
        return None
    try:
        normalized = stamp.replace("Z", "+00:00")
        ts = datetime.fromisoformat(normalized)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = datetime.now(timezone.utc) - ts.astimezone(timezone.utc)
        return max(0, int(delta.total_seconds() // 86400))
    except Exception:
        return None


def compute_verified_tag(payload: Dict[str, Any]) -> Dict[str, Any]:
    row = payload if isinstance(payload, dict) else {}
    settings = load_chain_rollout_registry(force_reload=False).get("settings", {})
    settings = settings if isinstance(settings, dict) else {}
    policy_version = _safe_text(settings.get("verified_tag_policy_version") or "verified_v1")
    reasons: List[str] = []

    if not bool(settings.get("verified_tag_release_enabled")):
        return {
            "verified_status": "disabled",
            "is_verified": False,
            "verified_reason_codes": ["global_kill_switch_off"],
            "verified_policy_version": policy_version,
        }

    chain_key = _norm_chain_key(row.get("matched_chain_key") or row.get("chain_key"))
    market = _norm_market(row.get("market") or row.get("country_code"))
    runtime = get_chain_runtime_config(chain_key, market) if chain_key and market else {}
    runtime = runtime if isinstance(runtime, dict) else {}
    features = runtime.get("features") if isinstance(runtime.get("features"), dict) else {}
    status = _safe_text(runtime.get("status") or row.get("chain_status")).lower()

    source = _source_token(row)
    confidence = _safe_float(row.get("menu_item_confidence"), _safe_float(row.get("order_confidence"), 0.0))
    is_generic = bool(row.get("best_item_is_generic_fallback"))
    specificity = _specificity_token(row)
    branch_conf = _safe_float(row.get("availability_confidence"), _safe_float(row.get("branch_availability_confidence"), 0.5))
    source_age = _source_age_days(row)
    min_conf = _safe_float(settings.get("verified_min_confidence"), 0.80)
    max_age = _safe_int(settings.get("verified_max_source_age_days"), 45)
    exact_tiers = {"exact_menu_match", "chain_registry", "menu_item_exact", "exact"}

    if source != "chain_registry":
        reasons.append("not_chain_backed_source")
    if status != "stable":
        reasons.append("chain_not_stable")
    if not bool(features.get("verified_enabled")):
        reasons.append("chain_verified_disabled")
    if is_generic:
        reasons.append("generic_fallback")
    if confidence < min_conf:
        reasons.append("low_confidence")
    if specificity and specificity not in exact_tiers:
        reasons.append("insufficient_specificity")
    if source_age is not None and source_age > max_age:
        reasons.append("stale_source")
    if branch_conf < 0.35:
        reasons.append("negative_branch_confidence")

    chain_backed_ok = source == "chain_registry"
    verified_candidate = chain_backed_ok and not reasons
    shadow_mode = bool(settings.get("verified_tag_shadow_mode")) or bool(features.get("verified_shadow_mode"))
    canary_ok = _is_in_canary(settings, row)

    if verified_candidate:
        status_value = "verified"
    elif chain_backed_ok:
        status_value = "chain_backed"
    else:
        trust = _safe_text(row.get("best_order_trust_tier") or row.get("recommended_order_trust_tier")).lower()
        status_value = trust if trust in {"estimated", "needs_menu_check"} else ("estimated" if confidence >= 0.55 else "needs_menu_check")

    is_verified_render = bool(verified_candidate and canary_ok and not shadow_mode)
    if verified_candidate and shadow_mode:
        reasons.append("shadow_mode")
    if verified_candidate and not canary_ok:
        reasons.append("outside_canary")
    if verified_candidate and is_verified_render:
        reasons.append("verified_eligible")

    return {
        "verified_status": status_value,
        "is_verified": bool(is_verified_render),
        "verified_reason_codes": reasons[:8] if reasons else (["verified_eligible"] if is_verified_render else []),
        "verified_policy_version": policy_version,
    }

