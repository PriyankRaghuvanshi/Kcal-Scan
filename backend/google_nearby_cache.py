"""
In-process TTL cache for Google Places Nearby results keyed by geohash + radius.

Reduces duplicate upstream calls when many users (or repeated opens) hit the same
area. Safe for multi-worker deployments only per process; add Redis later if needed.
"""
from __future__ import annotations

import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

# ~1.2 km x 0.6 km cells — good balance for urban restaurant density
_DEFAULT_PRECISION = 6
_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"

_CacheEntry = Tuple[List[Dict[str, Any]], Optional[str], Optional[int], float]
_store: Dict[str, _CacheEntry] = {}
_lock = threading.Lock()


def _encode_geohash(lat: float, lng: float, precision: int = _DEFAULT_PRECISION) -> str:
    lat = float(lat)
    lng = float(lng)
    idx = 0
    bit = 0
    even_bit = True
    lat_interval = (-90.0, 90.0)
    lng_interval = (-180.0, 180.0)
    geohash: List[str] = []
    while len(geohash) < precision:
        if even_bit:
            mid = (lng_interval[0] + lng_interval[1]) / 2
            if lng > mid:
                idx = idx * 2 + 1
                lng_interval = (mid, lng_interval[1])
            else:
                idx = idx * 2
                lng_interval = (lng_interval[0], mid)
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2
            if lat > mid:
                idx = idx * 2 + 1
                lat_interval = (mid, lat_interval[1])
            else:
                idx = idx * 2
                lat_interval = (lat_interval[0], mid)
        even_bit = not even_bit
        if bit < 4:
            bit += 1
        else:
            geohash.append(_BASE32[idx])
            bit = 0
            idx = 0
    return "".join(geohash)


def _cache_key(lat: float, lng: float, radius_m: int, precision: int) -> str:
    gh = _encode_geohash(lat, lng, precision)
    r = int(max(200, min(50000, int(radius_m))))
    return f"{gh}:{r}"


def cache_ttl_sec() -> int:
    raw = str(os.getenv("GOOGLE_NEARBY_CACHE_TTL_SEC", "300") or "300").strip()
    try:
        v = int(raw)
    except ValueError:
        v = 300
    return max(0, min(v, 3600))


def cache_enabled() -> bool:
    return str(os.getenv("GOOGLE_NEARBY_CACHE", "1")).strip().lower() in ("1", "true", "yes")


def geohash_precision() -> int:
    raw = str(os.getenv("GOOGLE_NEARBY_CACHE_GEOHASH_PRECISION", "6") or "6").strip()
    try:
        p = int(raw)
    except ValueError:
        p = 6
    return max(4, min(p, 8))


def get(lat: float, lng: float, radius_m: int) -> Optional[Tuple[List[Dict[str, Any]], Optional[str], Optional[int]]]:
    if not cache_enabled():
        return None
    ttl = cache_ttl_sec()
    if ttl <= 0:
        return None
    key = _cache_key(lat, lng, radius_m, geohash_precision())
    now = time.time()
    with _lock:
        row = _store.get(key)
        if not row:
            return None
        places, err, raw_count, expires = row
        if expires <= now:
            del _store[key]
            return None
    # Return shallow copies of list and dicts so callers cannot mutate cache
    places_copy = [dict(p) for p in places]
    return places_copy, err, raw_count


def set(
    lat: float,
    lng: float,
    radius_m: int,
    places: List[Dict[str, Any]],
    fetch_error_reason: Optional[str],
    raw_places_count: Optional[int],
) -> None:
    if not cache_enabled():
        return
    ttl = cache_ttl_sec()
    if ttl <= 0:
        return
    if fetch_error_reason:
        return
    key = _cache_key(lat, lng, radius_m, geohash_precision())
    expires = time.time() + ttl
    places_copy = [dict(p) for p in places]
    with _lock:
        _store[key] = (places_copy, fetch_error_reason, raw_places_count, expires)
        if len(_store) > 2000:
            _prune_unlocked(now=time.time())


def _prune_unlocked(*, now: float) -> None:
    dead = [k for k, v in _store.items() if v[3] <= now]
    for k in dead[:500]:
        _store.pop(k, None)
    if len(_store) > 2000:
        sorted_keys = sorted(_store.keys(), key=lambda k: _store[k][3])[:500]
        for k in sorted_keys:
            _store.pop(k, None)
