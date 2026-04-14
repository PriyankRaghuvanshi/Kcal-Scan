"""
Supabase-backed intelligence access for Healthy Nearby fast path.
Fails safely if DB unavailable. Falls back to JSON/file implementations.
No LLM. No live fetch.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TBL_VENUE_INTELLIGENCE_CACHE = "venue_intelligence_cache"
TBL_LOCAL_VENUE_PROFILES = "local_venue_profiles"
TBL_LOCAL_VENUE_TEMPLATES = "local_venue_templates"
TBL_LOCAL_VENUE_SWAPS = "local_venue_swaps"
TBL_ENRICHMENT_QUEUE = "enrichment_queue"
TBL_CHAIN_MENU_ITEMS = "chain_menu_items"
TBL_CHAIN_MENU_PROFILES = "chain_menu_profiles"
TBL_CHAIN_MATCH_EVENTS = "chain_match_events"
TBL_CHAIN_REGISTRY = "chain_registry"
_IMAGE_URL_FALLBACK_WARNED = False


def _supabase_available() -> bool:
    url = str(os.getenv("SUPABASE_URL") or "").strip()
    key = str(os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    return bool(url and key)


def _supabase_base_url() -> str:
    return f"{str(os.getenv('SUPABASE_URL') or '').strip().rstrip('/')}/rest/v1"


def _supabase_headers(prefer: Optional[str] = None) -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    h = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        h["Prefer"] = prefer
    return h


def _requests_module() -> Any:
    """Return requests module when installed, else None."""
    try:
        import requests  # type: ignore
        return requests
    except ModuleNotFoundError:
        return None


def _http_get_json(url: str, headers: Dict[str, str], params: Optional[Dict[str, str]] = None, timeout: int = 5) -> tuple[int, Any]:
    """
    Execute JSON GET using requests when available, else urllib.
    Returns (status_code, parsed_json_or_none). Raises on transport / HTTP errors.
    """
    requests = _requests_module()
    if requests is not None:
        resp = requests.get(url, headers=headers, params=params, timeout=timeout)
        resp.raise_for_status()
        return resp.status_code, resp.json() if resp.text else None

    qs = urlencode(params or {}, doseq=True)
    full_url = f"{url}?{qs}" if qs else url
    req = Request(full_url, headers=headers, method="GET")
    try:
        with urlopen(req, timeout=timeout) as resp:  # nosec B310
            body = resp.read().decode("utf-8", errors="ignore")
            return resp.status, json.loads(body) if body else None
    except HTTPError:
        raise
    except URLError:
        raise


def _http_post_json(
    url: str,
    headers: Dict[str, str],
    payload: Any,
    params: Optional[Dict[str, str]] = None,
    timeout: int = 30,
) -> tuple[int, Any]:
    """
    Execute JSON POST using requests when available, else urllib.
    Returns (status_code, parsed_json_or_none). Raises on transport / HTTP errors.
    """
    requests = _requests_module()
    if requests is not None:
        resp = requests.post(url, headers=headers, params=params, json=payload, timeout=timeout)
        resp.raise_for_status()
        return resp.status_code, resp.json() if resp.text else None

    qs = urlencode(params or {}, doseq=True)
    full_url = f"{url}?{qs}" if qs else url
    req = Request(
        full_url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(req, timeout=timeout) as resp:  # nosec B310
            body = resp.read().decode("utf-8", errors="ignore")
            return resp.status, json.loads(body) if body else None
    except HTTPError:
        raise
    except URLError:
        raise


def _sb_safe_get_one(table: str, params: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Safe Supabase get. Returns None on any error. Fails open for robustness."""
    if not _supabase_available():
        return None
    try:
        url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table}"
        headers = {
            "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
            "Content-Type": "application/json",
        }
        status, payload = _http_get_json(url, headers=headers, params=params, timeout=5)
        if status != 200:
            return None
        rows = payload or []
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
        url = f"{os.getenv('SUPABASE_URL')}/rest/v1/{table}"
        headers = {
            "apikey": os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""),
            "Authorization": f"Bearer {os.getenv('SUPABASE_SERVICE_ROLE_KEY', '')}",
            "Content-Type": "application/json",
        }
        status, payload = _http_get_json(url, headers=headers, params=params, timeout=5)
        if status != 200:
            return []
        rows = payload or []
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


def get_chain_menu_items(
    chain_key: str,
    market_tag: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Get chain menu items for a chain/market. Tries Supabase chain_menu_items first;
    falls back to chain_menu_ingestion (file store). Returns [] on any error. Fail-open.
    """
    key = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().upper()
    if not key:
        return []
    if _supabase_available():
        try:
            rows = _sb_safe_get_many(
                TBL_CHAIN_MENU_ITEMS,
                {"chain_key": f"eq.{key}", "market_tag": f"eq.{market}", "select": "*", "order": "item_key"},
            )
            if rows:
                return [dict(r) for r in rows]
            rows_au = _sb_safe_get_many(
                TBL_CHAIN_MENU_ITEMS,
                {"chain_key": f"eq.{key}", "market_tag": "eq.AU", "select": "*", "order": "item_key"},
            )
            if rows_au:
                return [dict(r) for r in rows_au]
        except Exception:
            pass
    try:
        from chain_menu_ingestion import get_chain_items
        return get_chain_items(key, market) or []
    except Exception:
        return []


def _chain_sync_debug() -> bool:
    """True if CHAIN_MENU_SYNC_DEBUG or SUPABASE_CHAIN_DEBUG is set (1/true/yes)."""
    v = (os.getenv("CHAIN_MENU_SYNC_DEBUG") or os.getenv("SUPABASE_CHAIN_DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _http_error_body(exc: Exception) -> str:
    """Best-effort extraction of HTTP error body across urllib / requests."""
    try:
        if hasattr(exc, "read"):
            body = exc.read()
            if isinstance(body, bytes):
                return body.decode("utf-8", errors="ignore")
            return str(body or "")
    except Exception:
        pass
    try:
        response = getattr(exc, "response", None)
        text = getattr(response, "text", "")
        if text:
            return str(text)
    except Exception:
        pass
    return ""


def _rows_without_optional_column(rows: List[Dict[str, Any]], column: str) -> List[Dict[str, Any]]:
    return [{k: v for k, v in row.items() if k != column} for row in rows]


def _should_retry_without_image_url(exc: Exception, rows: List[Dict[str, Any]]) -> bool:
    if not any("image_url" in row for row in rows):
        return False
    body = _http_error_body(exc)
    text = f"{repr(exc)}\n{body}".lower()
    return "image_url" in text and (
        "column" in text
        or "schema cache" in text
        or "could not find" in text
        or "does not exist" in text
    )


# Optional columns tied to later migrations. If the DB hasn't had the migration
# applied yet, PostgREST returns a "could not find column ... in schema cache"
# 400. We catch those and retry with the named column stripped.
_OPTIONAL_COLUMNS_WITH_MIGRATIONS = ("contains_palm_oil", "diet_type")


def _missing_optional_column(exc: Exception, rows: List[Dict[str, Any]]) -> Optional[str]:
    """Return the optional column name the DB is complaining about, or None."""
    body = _http_error_body(exc)
    text = f"{repr(exc)}\n{body}".lower()
    if not ("schema cache" in text or "could not find" in text or "does not exist" in text):
        return None
    for col in _OPTIONAL_COLUMNS_WITH_MIGRATIONS:
        if col in text and any(col in row for row in rows):
            return col
    return None


def upsert_chain_menu_profile(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Upsert one chain_menu_profiles row. Fail-open: returns None on error."""
    if not _supabase_available():
        if _chain_sync_debug():
            print("SUPABASE DEBUG upsert_chain_menu_profile: supabase not available")
        return None
    try:
        url = f"{_supabase_base_url()}/{TBL_CHAIN_MENU_PROFILES}"
        headers = _supabase_headers("resolution=merge-duplicates,return=representation")
        params = {"on_conflict": "chain_key,market_tag"}
        if _chain_sync_debug():
            print("SUPABASE DEBUG PROFILE POST url:", url, "params:", params, "row keys:", list(row.keys()))
        status, payload = _http_post_json(url, headers=headers, payload=[row], params=params, timeout=30)
        if _chain_sync_debug():
            print("SUPABASE DEBUG PROFILE POST status:", status)
        rows = payload or []
        return dict(rows[0]) if rows else dict(row)
    except Exception as e:
        if _chain_sync_debug():
            print("SUPABASE DEBUG upsert_chain_menu_profile ERROR:", repr(e))
        return None


def upsert_chain_registry_parent(chain_key: str, display_name: str) -> Optional[Dict[str, Any]]:
    """Ensure chain_registry parent row exists for chain_menu_items FK. Fail-open."""
    if not _supabase_available():
        if _chain_sync_debug():
            print("SUPABASE DEBUG upsert_chain_registry_parent: supabase not available")
        return None
    key = str(chain_key or "").strip().lower()
    label = str(display_name or "").strip() or key
    if not key:
        return None
    row = {"chain_key": key, "display_name": label}
    try:
        url = f"{_supabase_base_url()}/{TBL_CHAIN_REGISTRY}"
        headers = _supabase_headers("resolution=merge-duplicates,return=representation")
        params = {"on_conflict": "chain_key"}
        if _chain_sync_debug():
            print("SUPABASE DEBUG REGISTRY POST url:", url, "params:", params, "row:", row)
        status, payload = _http_post_json(url, headers=headers, payload=[row], params=params, timeout=30)
        if _chain_sync_debug():
            print("SUPABASE DEBUG REGISTRY POST status:", status)
        rows = payload or []
        return dict(rows[0]) if rows else dict(row)
    except HTTPError as e:
        if _chain_sync_debug():
            body = ""
            try:
                body = e.read().decode("utf-8", errors="ignore")
            except Exception:
                body = ""
            print("SUPABASE DEBUG upsert_chain_registry_parent ERROR:", repr(e))
            if body:
                print("SUPABASE DEBUG upsert_chain_registry_parent ERROR BODY:", body)
        return None
    except Exception as e:
        if _chain_sync_debug():
            print("SUPABASE DEBUG upsert_chain_registry_parent ERROR:", repr(e))
        return None


def upsert_chain_menu_items(chain_key: str, market_tag: str, items: List[Dict[str, Any]]) -> int:
    """Upsert chain menu items. Fail-open: returns 0 on error."""
    if not _supabase_available():
        if _chain_sync_debug():
            print("SUPABASE DEBUG upsert_chain_menu_items: supabase not available")
        return 0
    key = str(chain_key or "").strip().lower()
    market = str(market_tag or "AU").strip().upper()
    if not key:
        return 0
    rows = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        r = dict(item)
        r["chain_key"] = key
        r["market_tag"] = market
        rows.append(r)
    if _chain_sync_debug():
        print("SUPABASE DEBUG upsert_chain_menu_items rows_count:", len(rows))
    if not rows:
        return 0
    url = f"{_supabase_base_url()}/{TBL_CHAIN_MENU_ITEMS}"
    headers = _supabase_headers("resolution=merge-duplicates,return=minimal")
    params = {"on_conflict": "chain_key,market_tag,item_key"}

    # Retry loop: if PostgREST complains about a known optional column that
    # hasn't been migrated yet (image_url, contains_palm_oil, diet_type),
    # strip it and try again. Max 3 strips — one per optional col.
    attempt_rows = rows
    for _ in range(len(_OPTIONAL_COLUMNS_WITH_MIGRATIONS) + 1):
        try:
            status, _resp = _http_post_json(url, headers=headers, payload=attempt_rows, params=params, timeout=30)
            if _chain_sync_debug():
                print("SUPABASE DEBUG upsert_chain_menu_items POST status:", status)
            return len(attempt_rows)
        except Exception as e:
            missing = _missing_optional_column(e, attempt_rows)
            if missing is None:
                break
            if _chain_sync_debug():
                print(f"SUPABASE DEBUG upsert_chain_menu_items retrying without {missing} (migration missing?)")
            print(f"SUPABASE WARN chain_menu_items retrying without {missing}; run sql/add_palm_oil_and_diet_type.sql to persist this column.")
            attempt_rows = _rows_without_optional_column(attempt_rows, missing)
    # If we fell out of the retry loop (non-migration error), fall through to
    # legacy image_url-specific handling + the final error branch below.
    try:
        status, _resp = _http_post_json(url, headers=headers, payload=attempt_rows, params=params, timeout=30)
        if _chain_sync_debug():
            print("SUPABASE DEBUG upsert_chain_menu_items POST status:", status)
        return len(attempt_rows)
    except Exception as e:
        if _should_retry_without_image_url(e, rows):
            global _IMAGE_URL_FALLBACK_WARNED
            fallback_rows = _rows_without_optional_column(rows, "image_url")
            if not _IMAGE_URL_FALLBACK_WARNED:
                print("SUPABASE WARN chain_menu_items retrying without image_url; run sql/add_image_url_column.sql to persist thumbnails.")
                _IMAGE_URL_FALLBACK_WARNED = True
            if _chain_sync_debug():
                body = _http_error_body(e)
                print("SUPABASE DEBUG upsert_chain_menu_items retry_without_image_url:", True)
                print("SUPABASE DEBUG upsert_chain_menu_items ERROR:", repr(e))
                if body:
                    print("SUPABASE DEBUG upsert_chain_menu_items ERROR BODY:", body)
            try:
                status, _ = _http_post_json(url, headers=headers, payload=fallback_rows, params=params, timeout=30)
                if _chain_sync_debug():
                    print("SUPABASE DEBUG upsert_chain_menu_items POST status (no image_url):", status)
                return len(fallback_rows)
            except Exception as retry_exc:
                if _chain_sync_debug():
                    retry_body = _http_error_body(retry_exc)
                    print("SUPABASE DEBUG upsert_chain_menu_items RETRY ERROR:", repr(retry_exc))
                    if retry_body:
                        print("SUPABASE DEBUG upsert_chain_menu_items RETRY ERROR BODY:", retry_body)
                return 0
        if _chain_sync_debug():
            body = _http_error_body(e)
            print("SUPABASE DEBUG upsert_chain_menu_items ERROR:", repr(e))
            if body:
                print("SUPABASE DEBUG upsert_chain_menu_items ERROR BODY:", body)
        return 0


def insert_chain_match_events(events: List[Dict[str, Any]]) -> int:
    """
    Append-only insert of chain match impressions.
    Each row: {user_id?, chain_key, market_tag?, place_id?, was_top_pick?, ts?}
    Fail-open. Returns rows attempted (0 if Supabase unavailable).
    """
    if not _supabase_available():
        return 0
    rows: List[Dict[str, Any]] = []
    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        ck = str(ev.get("chain_key") or "").strip().lower()
        if not ck:
            continue
        rows.append({
            "user_id": str(ev.get("user_id") or "").strip() or None,
            "chain_key": ck,
            "market_tag": str(ev.get("market_tag") or "").strip().upper() or None,
            "place_id": str(ev.get("place_id") or "").strip() or None,
            "was_top_pick": bool(ev.get("was_top_pick")),
        })
    if not rows:
        return 0
    try:
        url = f"{_supabase_base_url()}/{TBL_CHAIN_MATCH_EVENTS}"
        headers = _supabase_headers("return=minimal")
        _http_post_json(url, headers=headers, payload=rows, timeout=15)
        return len(rows)
    except Exception:
        return 0


def chain_match_stats(days: int = 30, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Aggregate top chain matches in the last N days.
    Returns [{chain_key, market_tag, total, top_pick_count, distinct_users, distinct_places}, ...]
    Uses PostgREST RPC if available; falls back to client-side aggregation.
    """
    if not _supabase_available():
        return []
    days = max(1, min(int(days), 365))
    since_iso = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat().replace("+00:00", "Z")
    try:
        rows = _sb_safe_get_many(
            TBL_CHAIN_MATCH_EVENTS,
            {
                "select": "chain_key,market_tag,user_id,place_id,was_top_pick,ts",
                "ts": f"gte.{since_iso}",
                "limit": "100000",
            },
        )
    except Exception:
        return []
    agg: Dict[tuple, Dict[str, Any]] = {}
    for r in rows or []:
        if not isinstance(r, dict):
            continue
        ck = str(r.get("chain_key") or "").strip().lower()
        if not ck:
            continue
        mt = str(r.get("market_tag") or "").strip().upper()
        key = (ck, mt)
        cell = agg.setdefault(key, {
            "chain_key": ck, "market_tag": mt,
            "total": 0, "top_pick_count": 0,
            "_users": set(), "_places": set(),
        })
        cell["total"] += 1
        if bool(r.get("was_top_pick")):
            cell["top_pick_count"] += 1
        u = str(r.get("user_id") or "").strip()
        p = str(r.get("place_id") or "").strip()
        if u: cell["_users"].add(u)
        if p: cell["_places"].add(p)
    out = []
    for v in agg.values():
        out.append({
            "chain_key": v["chain_key"], "market_tag": v["market_tag"],
            "total": v["total"], "top_pick_count": v["top_pick_count"],
            "distinct_users": len(v["_users"]), "distinct_places": len(v["_places"]),
        })
    out.sort(key=lambda x: -x["total"])
    return out[:limit]


def list_chain_menu_chain_keys() -> List[str]:
    """Return sorted unique chain_key values from chain_menu_profiles. Fail-open: returns []."""
    if not _supabase_available():
        return []
    try:
        rows = _sb_safe_get_many(TBL_CHAIN_MENU_PROFILES, {"select": "chain_key"})
        keys = [str(r.get("chain_key") or "").strip() for r in rows if r.get("chain_key")]
        return sorted(set(k for k in keys if k))
    except Exception:
        return []


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
