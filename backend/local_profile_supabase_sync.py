"""
Sync trusted local venue profiles to Supabase canonical store.
Launches pack-seeded and auto-promoted profiles into one durable source of truth.
Idempotent. Fails safely when Supabase unavailable.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

SOURCE_PRECEDENCE = {
    "curated_manual": 4,
    "community_confirmed": 3,
    "auto_promoted": 2,
    "launch_enrichment_pack": 1,
    "bulk_enrichment_target": 0,
}


def _normalize_name(s: str) -> str:
    if not s or not isinstance(s, str):
        return ""
    return re.sub(r"[^\w\s]", "", re.sub(r"\s+", " ", str(s).strip().lower())).strip()


def _template_key(t: Dict[str, Any]) -> str:
    k = str(t.get("template_key") or "").strip()
    if k:
        return k
    n = str(t.get("template_name") or t.get("item_name") or "").strip()
    return re.sub(r"[^\w]+", "_", n.lower())[:64] if n else ""


def _source_rank(source: str) -> int:
    return SOURCE_PRECEDENCE.get(str(source or "").strip().lower(), 0)


def merge_trusted_profile_sources(
    existing: Optional[Dict[str, Any]],
    incoming: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge incoming profile into existing. Non-destructive.
    - Higher-priority source wins for profile-level fields.
    - New non-conflicting templates are appended.
    - Existing templates are not overwritten; confidence can be boosted.
    """
    if not existing:
        return dict(incoming)
    out = dict(existing)
    inc_src = str(incoming.get("profile_source") or "").strip().lower()
    ex_src = str(existing.get("profile_source") or "").strip().lower()
    if _source_rank(inc_src) <= _source_rank(ex_src):
        for k in ("profile_source", "seeded_by_launch_pack", "coverage_status"):
            if k in existing and existing[k] is not None:
                out[k] = existing[k]
    else:
        for k in ("profile_source", "seeded_by_launch_pack"):
            if k in incoming:
                out[k] = incoming[k]

    ex_templates = list(existing.get("candidate_templates") or [])
    ex_keys = {_template_key(t) for t in ex_templates if isinstance(t, dict) and _template_key(t)}
    inc_templates = list(incoming.get("candidate_templates") or [])
    for t in inc_templates:
        if not isinstance(t, dict):
            continue
        tk = _template_key(t)
        if not tk or tk in ex_keys:
            continue
        ex_templates.append(dict(t))
        ex_keys.add(tk)
    out["candidate_templates"] = ex_templates

    ex_swaps = list(existing.get("swap_templates") or [])
    ex_swap_keys = {str(s.get("swap_key") or "").strip() for s in ex_swaps if isinstance(s, dict)}
    inc_swaps = list(incoming.get("swap_templates") or [])
    for s in inc_swaps:
        if not isinstance(s, dict):
            continue
        sk = str(s.get("swap_key") or s.get("swap_label") or "").strip()[:32]
        if not sk or sk in ex_swap_keys:
            continue
        ex_swaps.append(dict(s))
        ex_swap_keys.add(sk)
    out["swap_templates"] = ex_swaps

    for k in ("name_variants", "cuisine_tags", "category_tags"):
        ex_v = set() if k == "cuisine_tags" else []
        if k == "cuisine_tags" or k == "category_tags":
            ex_v = set(str(x) for x in (existing.get(k) or [])) | set(str(x) for x in (incoming.get(k) or []))
            out[k] = list(ex_v)
        elif k == "name_variants":
            ex_v = set(str(x) for x in (existing.get(k) or [])) | set(str(x) for x in (incoming.get(k) or []))
            out[k] = list(ex_v)

    return out


def sync_launch_pack_profiles_to_supabase(
    area_key: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Sync launch-pack seeded profiles from JSON store to Supabase.
    Returns {synced, skipped, failed, errors}.
    """
    from local_launch_enrichment_pack import LAUNCH_ENRICHMENT_PACK, list_priority_local_venues
    from local_venue_profiles import get_profile_by_place_id, get_profile_by_normalized_name, _normalize_name
    from supabase_intelligence_store import get_local_venue_profile, upsert_trusted_profile_to_supabase

    areas = [area_key] if area_key else list(LAUNCH_ENRICHMENT_PACK.keys())[:min(limit, 20)]
    synced = 0
    skipped = 0
    failed = 0
    errors: List[str] = []

    for ak in areas[:limit]:
        venues = list_priority_local_venues(ak, limit=limit)
        for v in venues:
            pname = str(v.get("place_name") or "").strip()
            area = str(v.get("area_key") or ak or "").strip().lower()
            pid = str(v.get("place_id") or "").strip()
            if not pname and not pid:
                skipped += 1
                continue
            existing_sb = get_local_venue_profile(
                place_id=pid or None,
                normalized_name=_normalize_name(pname) if pname else None,
                area_key=area or None,
            )
            existing_json = get_profile_by_place_id(pid) if pid else get_profile_by_normalized_name(pname, area) if pname and area else None
            profile = merge_trusted_profile_sources(existing_sb or existing_json, dict(v))
            profile["profile_source"] = "launch_enrichment_pack"
            profile["seeded_by_launch_pack"] = True
            profile["area_key"] = area
            profile["place_name"] = pname or profile.get("place_name", "")
            profile["place_id"] = pid or profile.get("place_id", "")
            templates = profile.get("candidate_templates") or v.get("candidate_templates") or []
            swaps = profile.get("swap_templates") or v.get("swap_templates") or []
            result = upsert_trusted_profile_to_supabase(profile, templates=templates, swaps=swaps)
            if result:
                synced += 1
            else:
                failed += 1
                errors.append(f"{pname or pid}: upsert failed")

    return {
        "synced": synced,
        "skipped": skipped,
        "failed": failed,
        "errors": errors[:20],
        "area_key": area_key,
    }


def sync_auto_promoted_profiles_to_supabase(
    area_key: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Sync auto-promoted profiles from JSON store to Supabase.
    Collects profiles with auto_promoted/community_confirmed templates.
    """
    from local_venue_profiles import _profiles_list
    from supabase_intelligence_store import get_local_venue_profile, upsert_trusted_profile_to_supabase

    profiles = _profiles_list()
    has_auto = [
        p for p in profiles
        if any(
            str(t.get("profile_source") or "").strip() in ("auto_promoted", "community_confirmed")
            for t in (p.get("candidate_templates") or []) if isinstance(t, dict)
        )
    ]
    if area_key:
        area_norm = str(area_key or "").strip().lower()
        has_auto = [p for p in has_auto if str(p.get("area_key") or "").strip().lower() == area_norm]
    has_auto = has_auto[:limit]

    synced = 0
    failed = 0
    errors: List[str] = []
    for p in has_auto:
        pid = str(p.get("place_id") or "").strip()
        pname = str(p.get("place_name") or p.get("normalized_name") or "").strip()
        area = str(p.get("area_key") or "").strip().lower()
        if not pname and not pid:
            continue
        existing_sb = get_local_venue_profile(
            place_id=pid or None,
            normalized_name=_normalize_name(pname) if pname else None,
            area_key=area or None,
        )
        merged = merge_trusted_profile_sources(existing_sb, dict(p))
        result = upsert_trusted_profile_to_supabase(merged)
        if result:
            synced += 1
        else:
            failed += 1
            errors.append(f"{pname or pid}: upsert failed")

    return {
        "synced": synced,
        "failed": failed,
        "errors": errors[:20],
        "area_key": area_key,
    }


def sync_all_trusted_local_profiles(limit: int = 500) -> Dict[str, Any]:
    """
    Sync all trusted profiles (launch pack + auto-promoted) to Supabase.
    """
    pack_res = sync_launch_pack_profiles_to_supabase(area_key=None, limit=limit)
    auto_res = sync_auto_promoted_profiles_to_supabase(area_key=None, limit=limit)
    return {
        "launch_pack": pack_res,
        "auto_promoted": auto_res,
        "total_synced": pack_res.get("synced", 0) + auto_res.get("synced", 0),
        "total_failed": pack_res.get("failed", 0) + auto_res.get("failed", 0),
        "synced_at": datetime.now(timezone.utc).isoformat(),
    }


def get_sync_status(area_key: Optional[str] = None) -> Dict[str, Any]:
    """Status of canonical Supabase store vs local sources."""
    from local_venue_profiles import _profiles_list
    from local_launch_enrichment_pack import LAUNCH_ENRICHMENT_PACK
    from supabase_intelligence_store import (
        TBL_LOCAL_VENUE_PROFILES,
        _sb_safe_get_many,
        _supabase_available,
    )

    profiles = _profiles_list()
    if area_key:
        area_norm = str(area_key or "").strip().lower()
        profiles = [p for p in profiles if str(p.get("area_key") or "").strip().lower() == area_norm]

    pack_seeded = [p for p in profiles if p.get("seeded_by_launch_pack")]
    auto_promoted = [
        p for p in profiles
        if any(
            str(t.get("profile_source") or "").strip() in ("auto_promoted", "community_confirmed")
            for t in (p.get("candidate_templates") or []) if isinstance(t, dict)
        )
    ]

    canonical_count = 0
    if _supabase_available():
        if area_key:
            rows = _sb_safe_get_many(TBL_LOCAL_VENUE_PROFILES, {"area_key": f"eq.{area_key}", "select": "id"})
        else:
            rows = _sb_safe_get_many(TBL_LOCAL_VENUE_PROFILES, {"select": "id"})
        canonical_count = len(rows)

    pack_areas = list(LAUNCH_ENRICHMENT_PACK.keys()) if not area_key else [area_key]
    pack_venue_count = sum(len(LAUNCH_ENRICHMENT_PACK.get(ak, [])) for ak in pack_areas)

    return {
        "area_key": area_key,
        "supabase_available": _supabase_available(),
        "canonical_profile_count": canonical_count,
        "local_pack_seeded_count": len(pack_seeded),
        "local_auto_promoted_count": len(auto_promoted),
        "pack_venue_definitions": pack_venue_count,
    }
