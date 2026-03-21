from __future__ import annotations

"""
Deterministic, additive trust/evidence fields for "Best order right now".

This module MUST NOT change ranking/scoring. It is a pure post-process that
derives trust/evidence from existing fields (confidence_label, menu source,
menu confidence, evidence flags, etc.).
"""

from typing import Any, Dict, List, Optional
from verified_tagging import compute_verified_tag


_FEEDBACK_SIGNAL_CACHE: Dict[tuple[str, str], Dict[str, Any]] = {}
_FEEDBACK_SIGNAL_CACHE_MAX = 256


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _norm_text(x: Any) -> str:
    return " ".join(str(x or "").strip().split())


def _truthy(v: Any) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "y", "on")


def _normalize_source(src: Any) -> str:
    token = str(src or "").strip().lower()
    if token in {"menu_intelligence_store", "structured_menu", "scraped_menu", "website_menu", "website_text", "review_text", "ocr_menu"}:
        return "real_menu"
    if token in {"real_menu", "user_scan", "llm_inferred", "heuristic"}:
        return token
    if token in {"chain_registry", "ingested_chain_item"}:
        return "chain_registry"
    if token:
        return token
    return "heuristic"


def _trust_tier_from_existing(
    *,
    confidence_label: str,
    source: str,
    confidence: float,
    is_generic_fallback: bool,
) -> str:
    # Prefer the canonical existing label if present.
    lbl = str(confidence_label or "").strip()
    if lbl == "Verified":
        return "verified"
    if lbl == "Chain-backed":
        return "chain_backed"
    if lbl == "Estimated":
        return "estimated"
    if lbl == "Needs menu check":
        return "needs_menu_check"

    # Fallback mapping.
    if is_generic_fallback:
        return "needs_menu_check"
    if source == "chain_registry" and confidence >= 0.60:
        return "chain_backed"
    if source in {"real_menu", "user_scan"} and confidence >= 0.72:
        return "verified"
    if source == "llm_inferred" and confidence >= 0.55:
        return "estimated"
    if confidence >= 0.55:
        return "estimated"
    return "needs_menu_check"


def _evidence_strength(
    *,
    tier: str,
    source: str,
    confidence: float,
    strong_evidence: bool,
    is_generic_fallback: bool,
) -> float:
    conf = _clamp(_safe_float(confidence, 0.5), 0.0, 1.0)
    if is_generic_fallback:
        return float(min(0.65, conf))

    if tier == "verified":
        base = max(conf, 0.72)
        if source in {"real_menu", "user_scan"} and strong_evidence:
            base = min(0.99, base + 0.10)
        return float(_clamp(base, 0.0, 0.99))

    if tier == "chain_backed":
        base = max(conf, 0.60)
        return float(_clamp(base, 0.0, 0.95))

    if tier == "estimated":
        cap = 0.85 if strong_evidence else 0.78 if source == "llm_inferred" else 0.70
        return float(min(cap, conf))

    # needs_menu_check
    return float(min(0.65, conf))


def _summary_and_reasons(
    *,
    tier: str,
    source: str,
    strong_evidence: bool,
    is_generic_fallback: bool,
) -> Dict[str, Any]:
    reasons: List[str] = []

    if tier == "verified":
        if source in {"real_menu", "user_scan"}:
            reasons.append("Based on menu-backed item evidence.")
        elif source == "chain_registry":
            reasons.append("Chain-backed item match.")
        else:
            reasons.append("High-confidence item match.")
        if strong_evidence:
            reasons.append("Strong supporting menu signals.")
        summary = "Evidence-backed pick."
    elif tier == "chain_backed":
        reasons.append("Chain-backed item match.")
        summary = "Chain-backed pick."
    elif tier == "estimated":
        if source == "llm_inferred":
            reasons.append("Inferred from available menu text; confidence is moderate.")
        elif source == "heuristic":
            reasons.append("Estimated from limited menu evidence.")
        else:
            reasons.append("Estimated pick with moderate confidence.")
        summary = "Estimated pick — confirm if menu varies."
    else:
        # needs_menu_check
        if is_generic_fallback:
            reasons.append("Generic fallback — confirm on the menu for best accuracy.")
        else:
            reasons.append("Limited menu evidence — confirm on the menu.")
        summary = "Needs menu check."

    return {"summary": summary, "reasons": reasons[:4]}


def build_best_order_evidence_object(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(payload, dict):
        return None

    confidence_label = str(payload.get("confidence_label") or "").strip()
    source = _normalize_source(payload.get("menu_item_source") or payload.get("menu_source_resolved") or payload.get("menu_items_source_resolved"))
    confidence = _safe_float(payload.get("menu_item_confidence"), _safe_float(payload.get("order_confidence"), 0.5))
    is_generic = bool(payload.get("best_item_is_generic_fallback"))
    strong_evidence = bool(payload.get("best_order_strong_evidence") or payload.get("menu_item_strong_evidence") or payload.get("strong_evidence"))

    tier = _trust_tier_from_existing(
        confidence_label=confidence_label,
        source=source,
        confidence=float(confidence),
        is_generic_fallback=is_generic,
    )
    strength = _evidence_strength(
        tier=tier,
        source=source,
        confidence=float(confidence),
        strong_evidence=strong_evidence,
        is_generic_fallback=is_generic,
    )
    text = _summary_and_reasons(
        tier=tier,
        source=source,
        strong_evidence=strong_evidence,
        is_generic_fallback=is_generic,
    )

    # Additive enrichment only: incorporate user confirmation signals
    # into the evidence/trust layer without touching ranking math.
    tier, strength, text = _enrich_evidence_from_user_feedback(
        payload,
        tier=tier,
        strength=strength,
        text=text,
    )

    citation_url = _norm_text(payload.get("source_url") or payload.get("citation_url") or "")
    extraction_method = _norm_text(payload.get("extraction_method") or "")
    parse_method = _norm_text(payload.get("parse_method") or "")
    specificity_tier = _norm_text(payload.get("chosen_candidate_specificity_tier") or "")
    sources = [s for s in [source] if s]

    return {
        "trust_tier": tier,
        "strength": round(float(_clamp(strength, 0.0, 1.0)), 2),
        "summary": str(text["summary"]),
        "reasons": list(text["reasons"]),
        "sources": sources[:4],
        "citation_url": citation_url,
        "strong_evidence": bool(strong_evidence),
        "source": source,
        "confidence": round(float(_clamp(confidence, 0.0, 1.0)), 2),
        "source_rank_weight": round(float(_clamp(_safe_float(payload.get("source_rank_weight"), 0.0), 0.0, 1.1)), 2),
        "specificity_tier": specificity_tier,
        "extraction_method": extraction_method,
        "parse_method": parse_method,
        "generated_by": "rules_v1",
    }


def place_best_order_evidence_fields(place: Dict[str, Any], *, user_id: str = "") -> Dict[str, Any]:
    ev = build_best_order_evidence_object(place)
    if not ev:
        return {}
    verified = compute_verified_tag({**place, "best_order_trust_tier": ev.get("trust_tier"), "user_id": str(user_id or "")})
    return {
        "best_order_trust_tier": ev.get("trust_tier"),
        "best_order_evidence_strength": ev.get("strength"),
        "best_order_evidence_summary": ev.get("summary"),
        "best_order_evidence_reasons": ev.get("reasons"),
        "best_order_evidence_sources": ev.get("sources"),
        "best_order_citation_url": ev.get("citation_url"),
        "best_order_evidence": ev,
        "verified_status": verified.get("verified_status"),
        "is_verified": verified.get("is_verified"),
        "verified_reason_codes": verified.get("verified_reason_codes"),
        "verified_policy_version": verified.get("verified_policy_version"),
        "best_order_verified_status": verified.get("verified_status"),
        "best_order_is_verified": verified.get("is_verified"),
        "best_order_verified_reason_codes": verified.get("verified_reason_codes"),
        "best_order_verified_policy_version": verified.get("verified_policy_version"),
    }


def decision_card_evidence_fields(profile: Dict[str, Any], *, user_id: str = "") -> Dict[str, Any]:
    ev = build_best_order_evidence_object(profile)
    if not ev:
        return {}
    verified = compute_verified_tag({**profile, "recommended_order_trust_tier": ev.get("trust_tier"), "user_id": str(user_id or "")})
    return {
        "recommended_order_trust_tier": ev.get("trust_tier"),
        "recommended_order_evidence_strength": ev.get("strength"),
        "recommended_order_evidence_summary": ev.get("summary"),
        "recommended_order_evidence_reasons": ev.get("reasons"),
        "recommended_order_citation_url": ev.get("citation_url"),
        "verified_status": verified.get("verified_status"),
        "is_verified": verified.get("is_verified"),
        "verified_reason_codes": verified.get("verified_reason_codes"),
        "verified_policy_version": verified.get("verified_policy_version"),
        "recommended_order_verified_status": verified.get("verified_status"),
        "recommended_order_is_verified": verified.get("is_verified"),
        "recommended_order_verified_reason_codes": verified.get("verified_reason_codes"),
        "recommended_order_verified_policy_version": verified.get("verified_policy_version"),
    }


def evidence_flag_enabled(env: Optional[Dict[str, str]] = None) -> bool:
    import os
    src = env if isinstance(env, dict) else os.environ
    return _truthy(src.get("BEST_ORDER_EVIDENCE_V1"))


def _extract_feedback_place_id(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""
    place_id = payload.get("place_id") or payload.get("tracking", {}).get("place_id") or ""
    return str(place_id or "").strip()


def _extract_feedback_item_name(payload: Dict[str, Any]) -> str:
    if not isinstance(payload, dict):
        return ""

    # Mobile emits feedback for Decision cards using `recommended_order` (primary).
    candidates = [
        payload.get("recommended_order"),
        payload.get("best_item_name"),
        payload.get("best_order"),
        payload.get("tracking", {}).get("item"),
        payload.get("tracking", {}).get("recommended_order"),
    ]
    for c in candidates:
        s = str(c or "").strip()
        if s:
            return s
    return ""


def _cache_key_for_feedback(place_id: str, item_name: str) -> tuple[str, str]:
    # Keep cache stable against whitespace/case differences.
    pid = str(place_id or "").strip()
    inorm = " ".join(str(item_name or "").strip().lower().split())
    return (pid, inorm)


def _get_feedback_signal_cached(place_id: str, item_name: str) -> Optional[Dict[str, Any]]:
    if not place_id or not item_name:
        return None

    key = _cache_key_for_feedback(place_id, item_name)
    cached = _FEEDBACK_SIGNAL_CACHE.get(key)
    if isinstance(cached, dict):
        return cached

    try:
        from recommendation_feedback_store import get_place_item_feedback_signal

        signal = get_place_item_feedback_signal(place_id, item_name)
    except Exception:
        return None

    if not isinstance(signal, dict):
        return None

    if len(_FEEDBACK_SIGNAL_CACHE) >= _FEEDBACK_SIGNAL_CACHE_MAX:
        _FEEDBACK_SIGNAL_CACHE.clear()
    _FEEDBACK_SIGNAL_CACHE[key] = signal
    return signal


def _enrich_evidence_from_user_feedback(
    payload: Dict[str, Any],
    *,
    tier: str,
    strength: float,
    text: Dict[str, Any],
) -> tuple[str, float, Dict[str, Any]]:
    # Must remain additive and conservative: feedback modifies only evidence fields.
    place_id = _extract_feedback_place_id(payload)
    item_name = _extract_feedback_item_name(payload)
    if not place_id or not item_name:
        return tier, strength, text

    signal = _get_feedback_signal_cached(place_id, item_name)
    if not isinstance(signal, dict):
        return tier, strength, text

    if str(signal.get("signal_source") or "").strip().lower() != "place_item":
        return tier, strength, text

    n = int(_safe_float(signal.get("user_feedback_events_count"), 0.0) or 0)
    if n <= 0:
        return tier, strength, text

    A = _safe_float(signal.get("availability_confidence"), 0.0)
    O = _safe_float(signal.get("order_confirmation_rate"), 0.0)
    S = _safe_float(signal.get("sauce_default_confidence"), 0.0)
    P = _safe_float(signal.get("portion_reliability"), 0.0)

    user_reasons: List[str] = []
    strength_bump = 0.0

    if n >= 3 and A >= 0.75:
        user_reasons.append("User confirmed availability.")
        strength_bump += 0.05
    if n >= 2 and O >= 0.70:
        user_reasons.append("User confirmed they ordered this.")
        strength_bump += 0.03
    if n >= 2 and S >= 0.75:
        user_reasons.append("User confirmed sauce-by-default assumption.")
        strength_bump += 0.03
    if n >= 3 and P >= 0.70:
        user_reasons.append("User confirmed portion looked standard.")
        strength_bump += 0.02

    if user_reasons:
        base_reasons = text.get("reasons") if isinstance(text.get("reasons"), list) else []
        # Prepend user reasons so the drawer answers "why" first.
        merged = user_reasons + base_reasons
        text["reasons"] = merged[:4]
        strength = float(min(0.99, _clamp(strength + strength_bump, 0.0, 0.99)))

        # Optional tier upgrade: only needs_menu_check -> estimated.
        if tier == "needs_menu_check" and n >= 3 and A >= 0.80:
            tier = "estimated"

    return tier, strength, text

