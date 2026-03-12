"""
Supabase-backed intelligence access for Healthy Nearby fast path.
Fails safely if DB unavailable. Falls back to JSON/file implementations.
No LLM. No live fetch.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

TBL_VENUE_INTELLIGENCE_CACHE = "venue_intelligence_cache"
TBL_LOCAL_VENUE_PROFILES = "local_venue_profiles"
TBL_LOCAL_VENUE_TEMPLATES = "local_venue_templates"
TBL_LOCAL_VENUE_SWAPS = "local_venue_swaps"
TBL_ENRICHMENT_QUEUE = "enrichment_queue"


def _supabase_available() -> bool:
    url = str(os.getenv("SUPABASE_URL") or "").strip()
    key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    return bool(url and key)


def _sb_safe_get_one(table: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Safe Supabase get. Returns None on any error. Fails open for robustness."""
    if not _supabase_available():
        return None
    try:
        import requests
        url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table}"
        headers = {
            "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
            "Content-Type": "application/json",
        }
        r = requests.get(url, headers=headers, params=params, timeout=5)
        if r.status_code != 200:
            return None
        rows = r.json() or []
        if not rows or not isinstance(rows, list):
            return None
        row = rows[0] if isinstance(rows[0], dict) else {}
        return dict(row)
    except Exception:
        return None


def _sb_safe_get_many(table: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    if not _supabase_available():
        return []
    try:
        import requests
        url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table}"
        headers = {
            "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
            "Content-Type": "application/json",
        }
        r = requests.get(url, headers=headers, params=params, timeout=5)
        if r.status_code != 200:
            return []
        rows = r.json() or []
        return [dict(x) for x in rows if isinstance(x, dict)]
    except Exception:
        return []


def get_cached_venue_intelligence(place_id: str) -> Optional[Dict[str, Any]]:
    """
    Get cached venue intelligence for place_id.
    Tries Supabase first; falls back to venue_intelligence_cache JSON.
    """
    pid = str(place_id or "").strip()
    if not pid:
        return None
    row = _sb_safe_get_one(
        TBL_VENUE_INTELLIGENCE_CACHE,
        {"place_id": f"eq.{pid}", "select": "*", "limit": "1"},
    )
    if row:
        candidates = row.get("candidate_payload") or row.get("candidates")
        if isinstance(candidates, str):
            try:
                candidates = json.loads(candidates)
            except Exception:
                candidates = []
        swap_payload = row.get("swap_payload") or row.get("swap_templates")
        if isinstance(swap_payload, str):
            try:
                swap_payload = json.loads(swap_payload)
            except Exception:
                swap_payload = []
        return {
            "place_id": pid,
            "candidates": candidates if isinstance(candidates, list) else [],
            "candidate_payload": candidates if isinstance(candidates, list) else [],
            "swap_templates": swap_payload if isinstance(swap_payload, list) else [],
            "swap_payload": swap_payload if isinstance(swap_payload, list) else [],
            "source_type": str(row.get("source_type") or "exact_menu_cache"),
            "profile_source": str(row.get("profile_source") or "").strip() or None,
            "chosen_candidate_specificity_tier": str(row.get("chosen_candidate_specificity_tier") or "exact_menu_match"),
            "confidence": float(row.get("confidence") or 0.8),
            "last_enriched_at": row.get("last_enriched_at"),
            "source_url": str(row.get("source_url") or "").strip() or "",
            "from_supabase": True,
        }
    try:
        from venue_intelligence_cache import get as venue_cache_get
        cached = venue_cache_get(pid)
        if cached:
            cached.setdefault("profile_source", None)
            cached.setdefault("source_url", "")
        return cached
    except Exception:
        return None


def get_local_venue_profile(
    place_id: Optional[str] = None,
    normalized_name: Optional[str] = None,
    area_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Get local venue profile. place_id first; fallback to normalized_name + area_key.
    Tries Supabase first; falls back to local_venue_profiles JSON.
    """
    if place_id:
        row = _sb_safe_get_one(
            TBL_LOCAL_VENUE_PROFILES,
            {"place_id": f"eq.{place_id}", "select": "*", "limit": "1"},
        )
        if row and row.get("active", True):
            return _normalize_profile_row(row)
    if normalized_name and area_key:
        rows = _sb_safe_get_many(
            TBL_LOCAL_VENUE_PROFILES,
            {"area_key": f"eq.{area_key}", "select": "*"},
        )
        name_norm = _normalize_name(str(normalized_name or ""))
        for r in rows:
            if not r.get("active", True):
                continue
            variants = r.get("name_variants") or []
            base = _normalize_name(str(r.get("place_name") or r.get("normalized_name") or ""))
            if base:
                variants = [base] + list(variants)
            for v in variants:
                if _normalize_name(str(v)) == name_norm:
                    return _normalize_profile_row(r)
    from local_venue_profiles import get_profile_by_place_id, get_profile_by_normalized_name
    if place_id:
        return get_profile_by_place_id(place_id)
    if normalized_name and area_key:
        return get_profile_by_normalized_name(normalized_name, area_key)
    return None


def _normalize_name(s: str) -> str:
    import re
    return re.sub(r"[^\w\s]", "", re.sub(r"\s+", " ", str(s or "").strip().lower())).strip()


def _normalize_profile_row(row: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(row)
    templates = row.get("candidate_templates")
    if isinstance(templates, str):
        try:
            out["candidate_templates"] = json.loads(templates)
        except Exception:
            out["candidate_templates"] = []
    swaps = row.get("swap_templates")
    if isinstance(swaps, str):
        try:
            out["swap_templates"] = json.loads(swaps)
        except Exception:
            out["swap_templates"] = []
    return out


def get_local_venue_templates(profile_id: str) -> List[Dict[str, Any]]:
    """Get candidate templates for profile. From profile dict or separate table."""
    templates = _sb_safe_get_many(
        TBL_LOCAL_VENUE_TEMPLATES,
        {"profile_id": f"eq.{profile_id}", "select": "*"},
    )
    if templates:
        return [dict(t) for t in templates if isinstance(t, dict)]
    return []


def get_local_venue_swaps(profile_id: str) -> List[Dict[str, Any]]:
    """Get swap templates for profile."""
    swaps = _sb_safe_get_many(
        TBL_LOCAL_VENUE_SWAPS,
        {"profile_id": f"eq.{profile_id}", "select": "*"},
    )
    if swaps:
        return [dict(s) for s in swaps if isinstance(s, dict)]
    return []


def _sb_safe_upsert_local_profile(row: Dict[str, Any], on_conflict: str) -> Optional[Dict[str, Any]]:
    """Safe upsert to local_venue_profiles. Returns row or None. Does not raise."""
    if not _supabase_available():
        return None
    try:
        import requests
        url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{TBL_LOCAL_VENUE_PROFILES}"
        headers = {
            "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates,return=representation",
        }
        params = {"on_conflict": on_conflict}
        r = requests.post(url, headers=headers, params=params, data=json.dumps(row), timeout=10)
        if r.status_code not in (200, 201):
            return None
        rows = r.json() or []
        return dict(rows[0]) if rows else dict(row)
    except Exception:
        return None


def upsert_trusted_profile_to_supabase(
    profile: Dict[str, Any],
    templates: Optional[List[Dict[str, Any]]] = None,
    swaps: Optional[List[Dict[str, Any]]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Upsert a trusted local venue profile to Supabase canonical store.
    Idempotent: reruns merge safely without duplicates.
    Returns upserted row or None if Supabase unavailable.
    """
    pid = str(profile.get("place_id") or "").strip()
    area_key = str(profile.get("area_key") or "").strip().lower()
    place_name = str(profile.get("place_name") or profile.get("normalized_name") or "").strip()
    norm_name = _normalize_name(place_name)
    templates = templates if templates is not None else (profile.get("candidate_templates") or [])
    swaps = swaps if swaps is not None else (profile.get("swap_templates") or [])
    if not isinstance(templates, list):
        templates = []
    if not isinstance(swaps, list):
        swaps = []

    row = {
        "place_id": pid or None,
        "place_name": place_name,
        "normalized_name": norm_name,
        "name_variants": profile.get("name_variants") or [place_name] if place_name else [],
        "area_key": area_key,
        "profile_source": str(profile.get("profile_source") or "curated_manual").strip(),
        "seeded_by_launch_pack": bool(profile.get("seeded_by_launch_pack")),
        "candidate_templates": templates,
        "swap_templates": swaps,
        "coverage_status": str(profile.get("coverage_status") or "partial").strip(),
        "confidence_tier": float(profile.get("confidence_tier") or 0.78),
        "specificity_tier": str(profile.get("specificity_tier") or "enriched_local_profile").strip(),
        "active": bool(profile.get("active", True)),
        "cuisine_tags": profile.get("cuisine_tags") or [],
        "category_tags": profile.get("category_tags") or ["restaurant"],
        "market_tag": str(profile.get("market_tag") or "AU").strip(),
        "notes": str(profile.get("notes") or "").strip() or None,
    }
    if not row["place_name"] and not row["area_key"]:
        return None

    if pid:
        out = _sb_safe_upsert_local_profile(row, on_conflict="place_id")
        if out:
            return out

    existing = _sb_safe_get_many(
        TBL_LOCAL_VENUE_PROFILES,
        {"area_key": f"eq.{area_key}", "select": "id,place_id,normalized_name"},
    )
    for r in existing:
        if not r.get("place_id") and _normalize_name(str(r.get("normalized_name") or "")) == norm_name:
            try:
                import requests
                url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{TBL_LOCAL_VENUE_PROFILES}"
                rid = r.get("id")
                if not rid:
                    continue
                patch_url = f"{url}?id=eq.{rid}"
                headers = {
                    "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
                    "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
                    "Content-Type": "application/json",
                    "Prefer": "return=representation",
                }
                r2 = requests.patch(patch_url, headers=headers, data=json.dumps(row), timeout=10)
                if r2.status_code in (200, 204):
                    rows = r2.json() or []
                    return dict(rows[0]) if rows else dict(row)
            except Exception:
                pass
            break

    try:
        import requests
        url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{TBL_LOCAL_VENUE_PROFILES}"
        headers = {
            "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        r = requests.post(url, headers=headers, data=json.dumps(row), timeout=10)
        if r.status_code in (200, 201):
            rows = r.json() or []
            return dict(rows[0]) if rows else dict(row)
    except Exception:
        pass
    return None


def enqueue_place_for_enrichment(
    place: Dict[str, Any],
    *,
    reason: str = "candidate_low_specificity",
    area_key: Optional[str] = None,
    chain_key: Optional[str] = None,
    skip_recent_check: bool = False,
) -> None:
    """
    Enqueue place for background enrichment.
    Uses existing background_enrichment_queue. Dedupes recent enqueues.
    Skips if place was enqueued within last 24h (avoids queue spam).
    """
    from background_enrichment_queue import REASONS, enqueue as queue_enqueue
    reason = str(reason or "candidate_low_specificity").strip()
    if reason not in REASONS:
        reason = "candidate_low_specificity"
    place_id = str(place.get("place_id") or place.get("id") or "").strip()
    if not place_id:
        return
    if not skip_recent_check:
        try:
            from background_enrichment_queue import was_recently_enqueued
            if was_recently_enqueued(place_id, within_hours=24.0):
                return
        except Exception:
            pass
    place_name = str(place.get("name") or place.get("place_name") or "").strip()
    queue_enqueue(
        place_id,
        place_name=place_name,
        chain_match_key=chain_key,
        market=str(area_key or ""),
        reason_enqueued=reason,
    )
