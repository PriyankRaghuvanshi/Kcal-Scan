"""
Local venue profile schema and storage.
Semi-structured profiles for independents in launch suburbs.
No LLM. Deterministic. Cached.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
COVERAGE_STATUS = ("planned", "seeded", "partial", "strong")
PROFILE_SOURCE = ("curated_manual", "cached_user_feedback", "inferred_local_profile", "chain_registry", "hybrid", "auto_promoted", "community_confirmed", "launch_enrichment_pack", "bulk_enrichment_target")
SPECIFICITY_TIER = ("exact_local_profile", "enriched_local_profile", "heuristic_local_profile", "generic_fallback")

_PROFILES_VERSION = "v1"
_LOCK = threading.Lock()


def _profiles_path() -> Path:
    override = os.getenv("LOCAL_VENUE_PROFILES_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "local_venue_profiles.json"


def _normalize_name(name: str) -> str:
    if not name or not isinstance(name, str):
        return ""
    s = re.sub(r"\s+", " ", str(name).strip().lower())
    return re.sub(r"[^\w\s]", "", s).strip()


def _load_raw() -> Dict[str, Any]:
    path = _profiles_path()
    if not path.exists():
        return {"version": _PROFILES_VERSION, "profiles": []}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("profiles", [])
            return data
    except Exception:
        pass
    return {"version": _PROFILES_VERSION, "profiles": []}


def _profiles_list() -> List[Dict[str, Any]]:
    data = _load_raw()
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return []
    return [p for p in profiles if isinstance(p, dict) and p.get("active", True)]


def clear_profiles_cache() -> None:
    """Clear any module-level cache. Used by tests."""
    pass


def _indexed_profiles() -> tuple:
    """(by_place_id, by_normalized_area). Called with no args so lru_cache works."""
    profiles = _profiles_list()
    by_place_id: Dict[str, Dict[str, Any]] = {}
    by_normalized_area: Dict[str, List[Dict[str, Any]]] = {}
    for p in profiles:
        pid = str(p.get("place_id") or "").strip()
        if pid:
            by_place_id[pid] = p
        area = str(p.get("area_key") or "").strip().lower()
        if not area:
            continue
        name_variants = list(p.get("name_variants") or []) if isinstance(p.get("name_variants"), list) else []
        base_name = _normalize_name(p.get("place_name") or p.get("normalized_name") or "")
        if base_name:
            name_variants.insert(0, base_name)
        for nv in name_variants:
            norm = _normalize_name(nv) if isinstance(nv, str) else ""
            if not norm:
                continue
            key = f"{norm}::{area}"
            if key not in by_normalized_area:
                by_normalized_area[key] = []
            if p not in by_normalized_area[key]:
                by_normalized_area[key].append(p)
        if base_name:
            tokens = base_name.split()
            if len(tokens) >= 2:
                short = tokens[0]
                key_short = f"{short}::{area}"
                if key_short not in by_normalized_area:
                    by_normalized_area[key_short] = []
                if p not in by_normalized_area[key_short]:
                    by_normalized_area[key_short].append(p)
    return (by_place_id, by_normalized_area)


def get_profile_by_place_id(place_id: str) -> Optional[Dict[str, Any]]:
    """Match by place_id when available."""
    pid = str(place_id or "").strip()
    if not pid:
        return None
    by_place_id, _ = _indexed_profiles()
    return dict(by_place_id[pid]) if pid in by_place_id else None


def get_profile_by_normalized_name(place_name: str, area_key: str) -> Optional[Dict[str, Any]]:
    """Fallback match by normalized_name + area_key. Avoids cross-area false matches."""
    norm = _normalize_name(place_name)
    area = str(area_key or "").strip().lower()
    if not norm or not area:
        return None
    key = f"{norm}::{area}"
    _, by_norm_area = _indexed_profiles()
    matches = by_norm_area.get(key, [])
    if not matches:
        return None
    return dict(matches[0])


def match_local_profile(
    place: Dict[str, Any],
    area_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Match a place to a local venue profile.
    Uses place_id first, then fallback by normalized_name + area_key.
    """
    place_id = str(place.get("place_id") or place.get("id") or "").strip()
    profile = get_profile_by_place_id(place_id) if place_id else None
    if profile:
        return profile
    place_name = str(place.get("name") or place.get("place_name") or "").strip()
    if not place_name or not area_key:
        return None
    return get_profile_by_normalized_name(place_name, area_key)


def profile_to_candidates(profile: Dict[str, Any], max_items: int = 6) -> List[Dict[str, Any]]:
    """Convert profile candidate_templates to menu-item shape for downstream."""
    templates = profile.get("candidate_templates")
    if not isinstance(templates, list):
        return []
    active = [x for x in templates if isinstance(x, dict) and not x.get("inactive")]
    out = []
    for t in active[:max_items]:
        if not isinstance(t, dict):
            continue
        name = str(t.get("template_name") or t.get("item_name") or "").strip()
        if not name:
            continue
        item = {
            "item_name": name,
            "template_key": str(t.get("template_key") or "").strip(),
            "estimated_calories": int(t.get("estimated_calories") or 520),
            "estimated_protein_g": int(t.get("estimated_protein_g") or 28),
            "menu_item_source": "enriched_local_profile",
            "menu_item_confidence": float(t.get("confidence") or 0.78),
            "specificity_tier": profile.get("specificity_tier") or "enriched_local_profile",
            "profile_source": t.get("profile_source") or profile.get("profile_source") or "curated_manual",
            "cut_friendly": bool(t.get("cut_friendly", False)),
            "food_quality_tags": t.get("food_quality_tags") or [],
        }
        if t.get("vegetarian_possible") is not None:
            item["vegetarian_possible"] = bool(t.get("vegetarian_possible"))
        if t.get("vegan_possible") is not None:
            item["vegan_possible"] = bool(t.get("vegan_possible"))
        if t.get("diet_tags"):
            item["diet_tags"] = list(t.get("diet_tags"))
        out.append(item)
    return out


def profile_to_swaps(profile: Dict[str, Any], template_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """Get swap templates from profile, optionally filtered by template_key."""
    swaps = profile.get("swap_templates")
    if not isinstance(swaps, list):
        return []
    out = []
    rec_keys = set()
    if template_key:
        for t in profile.get("candidate_templates") or []:
            if isinstance(t, dict) and str(t.get("template_key")) == str(template_key):
                rec_keys = set(t.get("recommended_swap_keys") or [])
                break
    for s in swaps:
        if not isinstance(s, dict):
            continue
        sk = str(s.get("swap_key") or "").strip()
        if template_key and rec_keys and sk not in rec_keys:
            continue
        out.append({
            "swap_key": sk,
            "swap_label": str(s.get("swap_label") or sk).strip(),
            "swap_type": str(s.get("swap_type") or "custom").strip(),
            "calories_delta": int(s.get("calories_delta") or 0),
            "protein_delta": int(s.get("protein_delta") or 0),
            "reason": str(s.get("reason") or "").strip(),
            "plausibility_score": float(s.get("plausibility_score") or 0.85),
        })
    return out


def validate_profile_schema(profile: Dict[str, Any]) -> List[str]:
    """Validate profile schema. Returns list of error strings."""
    errs = []
    if not str(profile.get("place_id") or "").strip() and not str(profile.get("place_name") or "").strip():
        errs.append("place_id or place_name required")
    if not str(profile.get("area_key") or "").strip():
        errs.append("area_key required")
    cov = str(profile.get("coverage_status") or "").strip()
    if cov and cov not in COVERAGE_STATUS:
        errs.append(f"coverage_status must be one of {COVERAGE_STATUS}")
    src = str(profile.get("profile_source") or "").strip()
    if src and src not in PROFILE_SOURCE:
        errs.append(f"profile_source must be one of {PROFILE_SOURCE}")
    tier = str(profile.get("specificity_tier") or "").strip()
    if tier and tier not in SPECIFICITY_TIER:
        errs.append(f"specificity_tier must be one of {SPECIFICITY_TIER}")
    templates = profile.get("candidate_templates")
    if not isinstance(templates, list) or len(templates) == 0:
        errs.append("candidate_templates must be non-empty list")
    return errs


def _all_profiles_raw() -> List[Dict[str, Any]]:
    """Load all profiles (including inactive) for mutation."""
    data = _load_raw()
    profiles = data.get("profiles")
    if not isinstance(profiles, list):
        return []
    return list(profiles)


def _save_profiles(profiles: List[Dict[str, Any]]) -> None:
    """Save profiles list back to disk."""
    path = _profiles_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = _load_raw()
    data["profiles"] = profiles
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _profile_matches(profile: Dict[str, Any], place_id: str, place_name: str, area_key: str) -> bool:
    """True if profile matches place_id or (place_name + area_key)."""
    pid = str(place_id or "").strip()
    pname_norm = _normalize_name(place_name or "")
    area = str(area_key or "").strip().lower()
    if pid and str(profile.get("place_id") or "").strip() == pid:
        return True
    if not pname_norm or not area:
        return False
    prof_area = str(profile.get("area_key") or "").strip().lower()
    if prof_area != area:
        return False
    name_variants = list(profile.get("name_variants") or [])
    base = _normalize_name(profile.get("place_name") or profile.get("normalized_name") or "")
    if base:
        name_variants.insert(0, base)
    for nv in name_variants:
        if _normalize_name(nv) == pname_norm:
            return True
    return _normalize_name(profile.get("place_name") or "") == pname_norm


def add_candidate_template(
    place_id: str,
    place_name: str,
    area_key: str,
    template: Dict[str, Any],
    *,
    profile_source: str = "cached_user_feedback",
) -> bool:
    """
    Add a candidate template to a profile. Creates profile if missing.
    template must have template_key, template_name; optional estimated_calories, estimated_protein_g, etc.
    Returns True if applied.
    """
    pid = str(place_id or "").strip()
    pname = str(place_name or "").strip()
    area = str(area_key or "").strip().lower()
    if not pname and not pid:
        return False

    template_key = str(template.get("template_key") or "").strip()
    template_name = str(template.get("template_name") or template.get("item_name") or "").strip()
    if not template_key:
        import re
        template_key = re.sub(r"[^\w]+", "_", template_name.lower())[:64]
    if not template_name:
        return False

    with _LOCK:
        profiles = _all_profiles_raw()
        found_idx = None
        for i, p in enumerate(profiles):
            if _profile_matches(p, pid, pname, area):
                found_idx = i
                break

        if found_idx is not None:
            p = profiles[found_idx]
            templates = list(p.get("candidate_templates") or [])
            existing_keys = {str(t.get("template_key") or "").strip() for t in templates if isinstance(t, dict)}
            if template_key in existing_keys:
                return False
            new_t = {
                "template_key": template_key,
                "template_name": template_name,
                "estimated_calories": int(template.get("estimated_calories") or 520),
                "estimated_protein_g": int(template.get("estimated_protein_g") or 28),
                "confidence": float(template.get("confidence") or 0.75),
                "food_quality_tags": list(template.get("food_quality_tags") or []),
                "negative_flags": list(template.get("negative_flags") or []),
                "cut_friendly": bool(template.get("cut_friendly", True)),
                "recommended_swap_keys": list(template.get("recommended_swap_keys") or []),
            }
            if template.get("diet_tags"):
                new_t["diet_tags"] = list(template.get("diet_tags"))
            if template.get("vegetarian_possible") is not None:
                new_t["vegetarian_possible"] = bool(template.get("vegetarian_possible"))
            if template.get("vegan_possible") is not None:
                new_t["vegan_possible"] = bool(template.get("vegan_possible"))
            if template.get("promoted_from_contribution_ids"):
                new_t["promoted_from_contribution_ids"] = list(template.get("promoted_from_contribution_ids"))
            if template.get("promoted_at"):
                new_t["promoted_at"] = str(template.get("promoted_at"))
            if template.get("evidence_score") is not None:
                new_t["evidence_score"] = int(template.get("evidence_score"))
            if template.get("profile_source"):
                new_t["profile_source"] = str(template.get("profile_source"))
            if template.get("support_count") is not None:
                new_t["support_count"] = int(template.get("support_count"))
            templates.append(new_t)
            p["candidate_templates"] = templates
            p["profile_source"] = profile_source
            _save_profiles(profiles)
            return True

        new_profile = {
            "place_id": pid,
            "place_name": pname,
            "normalized_name": _normalize_name(pname),
            "name_variants": [pname],
            "area_key": area,
            "market_tag": "AU",
            "cuisine_tags": [],
            "category_tags": ["restaurant"],
            "coverage_status": "seeded",
            "confidence_tier": 0.75,
            "profile_source": profile_source,
            "specificity_tier": "enriched_local_profile",
            "active": True,
            "candidate_templates": [{
                "template_key": template_key,
                "template_name": template_name,
                "estimated_calories": int(template.get("estimated_calories") or 520),
                "estimated_protein_g": int(template.get("estimated_protein_g") or 28),
                "confidence": float(template.get("confidence") or 0.75),
                "food_quality_tags": list(template.get("food_quality_tags") or []),
                "negative_flags": list(template.get("negative_flags") or []),
                "cut_friendly": bool(template.get("cut_friendly", True)),
                "recommended_swap_keys": [],
            }],
            "swap_templates": [],
        }
        if template.get("diet_tags"):
            new_profile["candidate_templates"][0]["diet_tags"] = list(template.get("diet_tags"))
        if template.get("vegetarian_possible") is not None:
            new_profile["candidate_templates"][0]["vegetarian_possible"] = bool(template.get("vegetarian_possible"))
        if template.get("vegan_possible") is not None:
            new_profile["candidate_templates"][0]["vegan_possible"] = bool(template.get("vegan_possible"))
        if template.get("promoted_from_contribution_ids"):
            new_profile["candidate_templates"][0]["promoted_from_contribution_ids"] = list(template.get("promoted_from_contribution_ids"))
        if template.get("promoted_at"):
            new_profile["candidate_templates"][0]["promoted_at"] = str(template.get("promoted_at"))
        if template.get("evidence_score") is not None:
            new_profile["candidate_templates"][0]["evidence_score"] = int(template.get("evidence_score"))
        if template.get("profile_source"):
            new_profile["candidate_templates"][0]["profile_source"] = str(template.get("profile_source"))
        if template.get("support_count") is not None:
            new_profile["candidate_templates"][0]["support_count"] = int(template.get("support_count"))
        profiles.append(new_profile)
        _save_profiles(profiles)
        return True


def add_swap_template(
    place_id: str,
    place_name: str,
    area_key: str,
    swap: Dict[str, Any],
) -> bool:
    """Add a swap template to a profile. Returns True if applied."""
    pid = str(place_id or "").strip()
    pname = str(place_name or "").strip()
    area = str(area_key or "").strip().lower()
    if not pname and not pid:
        return False

    swap_key = str(swap.get("swap_key") or "").strip()
    if not swap_key:
        swap_key = str(swap.get("swap_label") or "custom")[:32]

    with _LOCK:
        profiles = _all_profiles_raw()
        for p in profiles:
            if _profile_matches(p, pid, pname, area):
                swaps = list(p.get("swap_templates") or [])
                existing = {str(s.get("swap_key") or "").strip() for s in swaps if isinstance(s, dict)}
                if swap_key in existing:
                    return False
                swaps.append({
                    "swap_key": swap_key,
                    "swap_label": str(swap.get("swap_label") or swap_key).strip(),
                    "swap_type": str(swap.get("swap_type") or "custom").strip(),
                    "calories_delta": int(swap.get("calories_delta") or 0),
                    "protein_delta": int(swap.get("protein_delta") or 0),
                    "reason": str(swap.get("reason") or "").strip(),
                    "plausibility_score": float(swap.get("plausibility_score") or 0.85),
                })
                p["swap_templates"] = swaps
                _save_profiles(profiles)
                return True
    return False


def upsert_profile_from_pack(
    venue_def: Dict[str, Any],
    *,
    profile_source: str = "launch_enrichment_pack",
) -> Dict[str, Any]:
    """
    Create or extend a local venue profile from an enrichment pack definition.
    venue_def: place_name, name_variants, area_key, cuisine_tags, category_tags,
               candidate_templates, swap_templates, notes, place_id?
    Returns {created: bool, templates_added: int, swaps_added: int}.
    """
    import re as _re
    pname = str(venue_def.get("place_name") or "").strip()
    area = str(venue_def.get("area_key") or "").strip().lower()
    pid = str(venue_def.get("place_id") or "").strip()
    if not pname and not pid:
        return {"created": False, "templates_added": 0, "swaps_added": 0, "error": "place_name or place_id required"}

    name_variants = list(venue_def.get("name_variants") or [])
    if pname and pname not in name_variants:
        name_variants.insert(0, pname)
    if not name_variants and pname:
        name_variants = [pname]

    cuisine_tags = list(venue_def.get("cuisine_tags") or [])
    category_tags = list(venue_def.get("category_tags") or ["restaurant"])
    candidate_templates = list(venue_def.get("candidate_templates") or [])
    swap_templates = list(venue_def.get("swap_templates") or [])
    notes = str(venue_def.get("notes") or "").strip()

    templates_added = 0
    swaps_added = 0
    created = False

    with _LOCK:
        profiles = _all_profiles_raw()
        found_idx = None
        for i, p in enumerate(profiles):
            if _profile_matches(p, pid, pname, area):
                found_idx = i
                break

        if found_idx is not None:
            p = profiles[found_idx]
            existing_templates = list(p.get("candidate_templates") or [])
            existing_keys = {str(t.get("template_key") or "").strip() for t in existing_templates if isinstance(t, dict)}
            existing_swaps = list(p.get("swap_templates") or [])
            existing_swap_keys = {str(s.get("swap_key") or "").strip() for s in existing_swaps if isinstance(s, dict)}

            for t in candidate_templates:
                tk = str(t.get("template_key") or "").strip()
                if not tk:
                    tk = _re.sub(r"[^\w]+", "_", str(t.get("template_name") or "").lower())[:64]
                if tk and tk not in existing_keys:
                    new_t = {
                        "template_key": tk,
                        "template_name": str(t.get("template_name") or t.get("item_name") or "").strip(),
                        "estimated_calories": int(t.get("estimated_calories") or 520),
                        "estimated_protein_g": int(t.get("estimated_protein_g") or 28),
                        "confidence": float(t.get("confidence") or 0.78),
                        "food_quality_tags": list(t.get("food_quality_tags") or []),
                        "negative_flags": list(t.get("negative_flags") or []),
                        "cut_friendly": bool(t.get("cut_friendly", True)),
                        "recommended_swap_keys": list(t.get("recommended_swap_keys") or []),
                    }
                    if t.get("diet_tags"):
                        new_t["diet_tags"] = list(t.get("diet_tags"))
                    if t.get("vegetarian_possible") is not None:
                        new_t["vegetarian_possible"] = bool(t.get("vegetarian_possible"))
                    if t.get("vegan_possible") is not None:
                        new_t["vegan_possible"] = bool(t.get("vegan_possible"))
                    existing_templates.append(new_t)
                    existing_keys.add(tk)
                    templates_added += 1

            for s in swap_templates:
                sk = str(s.get("swap_key") or "").strip()
                if not sk:
                    sk = str(s.get("swap_label") or "custom")[:32]
                if sk and sk not in existing_swap_keys:
                    existing_swaps.append({
                        "swap_key": sk,
                        "swap_label": str(s.get("swap_label") or sk).strip(),
                        "swap_type": str(s.get("swap_type") or "custom").strip(),
                        "calories_delta": int(s.get("calories_delta") or 0),
                        "protein_delta": int(s.get("protein_delta") or 0),
                        "reason": str(s.get("reason") or "").strip(),
                        "plausibility_score": float(s.get("plausibility_score") or 0.85),
                    })
                    existing_swap_keys.add(sk)
                    swaps_added += 1

            p["candidate_templates"] = existing_templates
            p["swap_templates"] = existing_swaps
            p["profile_source"] = profile_source
            p["seeded_by_launch_pack"] = True
            if cuisine_tags:
                p["cuisine_tags"] = list(set(list(p.get("cuisine_tags") or []) + cuisine_tags))
            if name_variants:
                p["name_variants"] = list(set(list(p.get("name_variants") or []) + name_variants))
            if len(existing_templates) >= 3:
                p["coverage_status"] = "strong"
            elif len(existing_templates) >= 1:
                p["coverage_status"] = "partial"
            if notes:
                p["notes"] = notes
            _save_profiles(profiles)
            return {"created": False, "templates_added": templates_added, "swaps_added": swaps_added}

        new_profile = {
            "place_id": pid,
            "place_name": pname,
            "normalized_name": _normalize_name(pname),
            "name_variants": name_variants or [pname],
            "area_key": area,
            "market_tag": str(venue_def.get("market_tag") or "AU"),
            "cuisine_tags": cuisine_tags,
            "category_tags": category_tags[:10],
            "coverage_status": "strong" if len(candidate_templates) >= 3 else "partial" if candidate_templates else "seeded",
            "confidence_tier": float(venue_def.get("confidence_tier") or 0.78),
            "profile_source": profile_source,
            "specificity_tier": "enriched_local_profile",
            "active": True,
            "seeded_by_launch_pack": True,
            "candidate_templates": [],
            "swap_templates": [],
        }
        if notes:
            new_profile["notes"] = notes

        for t in candidate_templates:
            tk = str(t.get("template_key") or "").strip()
            tn = str(t.get("template_name") or t.get("item_name") or "").strip()
            if not tk:
                tk = _re.sub(r"[^\w]+", "_", tn.lower())[:64]
            if tn:
                nt = {
                    "template_key": tk,
                    "template_name": tn,
                    "estimated_calories": int(t.get("estimated_calories") or 520),
                    "estimated_protein_g": int(t.get("estimated_protein_g") or 28),
                    "confidence": float(t.get("confidence") or 0.78),
                    "food_quality_tags": list(t.get("food_quality_tags") or []),
                    "negative_flags": list(t.get("negative_flags") or []),
                    "cut_friendly": bool(t.get("cut_friendly", True)),
                    "recommended_swap_keys": list(t.get("recommended_swap_keys") or []),
                }
                if t.get("diet_tags"):
                    nt["diet_tags"] = list(t.get("diet_tags"))
                if t.get("vegetarian_possible") is not None:
                    nt["vegetarian_possible"] = bool(t.get("vegetarian_possible"))
                if t.get("vegan_possible") is not None:
                    nt["vegan_possible"] = bool(t.get("vegan_possible"))
                new_profile["candidate_templates"].append(nt)
                templates_added += 1

        for s in swap_templates:
            sk = str(s.get("swap_key") or "").strip() or str(s.get("swap_label") or "custom")[:32]
            new_profile["swap_templates"].append({
                "swap_key": sk,
                "swap_label": str(s.get("swap_label") or sk).strip(),
                "swap_type": str(s.get("swap_type") or "custom").strip(),
                "calories_delta": int(s.get("calories_delta") or 0),
                "protein_delta": int(s.get("protein_delta") or 0),
                "reason": str(s.get("reason") or "").strip(),
                "plausibility_score": float(s.get("plausibility_score") or 0.85),
            })
            swaps_added += 1

        if new_profile["candidate_templates"]:
            profiles.append(new_profile)
            _save_profiles(profiles)
            created = True

    return {"created": created, "templates_added": templates_added, "swaps_added": swaps_added}


def update_template_in_profile(
    place_id: str,
    place_name: str,
    area_key: str,
    template_key: str,
    updates: Dict[str, Any],
) -> bool:
    """
    Update an existing template. Use for: inactive=True, confidence=0.5, notes.
    Does not delete; prefers inactive/confidence adjustments.
    """
    pid = str(place_id or "").strip()
    pname = str(place_name or "").strip()
    area = str(area_key or "").strip().lower()
    tk = str(template_key or "").strip()
    if not tk:
        return False

    with _LOCK:
        profiles = _all_profiles_raw()
        for p in profiles:
            if _profile_matches(p, pid, pname, area):
                templates = p.get("candidate_templates") or []
                for t in templates:
                    if isinstance(t, dict) and str(t.get("template_key") or "").strip() == tk:
                        for k, v in updates.items():
                            if k in ("inactive", "confidence", "notes", "negative_flags", "cut_friendly"):
                                t[k] = v
                        _save_profiles(profiles)
                        return True
    return False
