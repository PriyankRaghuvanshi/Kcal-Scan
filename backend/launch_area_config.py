"""
Launch area configuration for local venue enrichment.
Focus on Sydney-west launch geography.
No LLM. Deterministic.
"""
from __future__ import annotations

import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_RADIUS_M = 1500
_EARTH_RADIUS_M = 6_371_000


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _default_launch_areas() -> List[Dict[str, Any]]:
    """Sydney-west launch suburbs. Center coords approximate."""
    return [
        {"area_key": "wentworthville", "display_name": "Wentworthville", "center_lat": -33.8155, "center_lng": 150.9675, "radius_m": 1200, "market_tag": "AU", "enabled": True},
        {"area_key": "parramatta", "display_name": "Parramatta", "center_lat": -33.8150, "center_lng": 150.9992, "radius_m": 2000, "market_tag": "AU", "enabled": True},
        {"area_key": "harris_park", "display_name": "Harris Park", "center_lat": -33.8240, "center_lng": 151.0070, "radius_m": 800, "market_tag": "AU", "enabled": True},
        {"area_key": "westmead", "display_name": "Westmead", "center_lat": -33.8050, "center_lng": 150.9880, "radius_m": 1200, "market_tag": "AU", "enabled": True},
        {"area_key": "merrylands", "display_name": "Merrylands", "center_lat": -33.8337, "center_lng": 150.9880, "radius_m": 1500, "market_tag": "AU", "enabled": True},
        {"area_key": "granville", "display_name": "Granville", "center_lat": -33.8340, "center_lng": 150.9920, "radius_m": 1000, "market_tag": "AU", "enabled": True},
        {"area_key": "homebush", "display_name": "Homebush", "center_lat": -33.8667, "center_lng": 151.0833, "radius_m": 1200, "market_tag": "AU", "enabled": True},
        {"area_key": "strathfield", "display_name": "Strathfield", "center_lat": -33.8745, "center_lng": 151.0930, "radius_m": 1500, "market_tag": "AU", "enabled": True},
        {"area_key": "sydney_olympic_park", "display_name": "Sydney Olympic Park", "center_lat": -33.8474, "center_lng": 151.0695, "radius_m": 2000, "market_tag": "AU", "enabled": True},
    ]


def _load_config() -> List[Dict[str, Any]]:
    override = os.getenv("LAUNCH_AREA_CONFIG_PATH", "").strip()
    if override:
        path = Path(override)
        if path.exists():
            try:
                import json
                with path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and isinstance(data.get("areas"), list):
                    return data["areas"]
                if isinstance(data, list):
                    return data
            except Exception:
                pass
    return _default_launch_areas()


def list_launch_areas(*, enabled_only: bool = True) -> List[Dict[str, Any]]:
    """List all launch areas. Optionally filter to enabled only."""
    areas = _load_config()
    if enabled_only:
        areas = [a for a in areas if a.get("enabled", True)]
    return [dict(a) for a in areas]


def get_launch_area(area_key: str) -> Optional[Dict[str, Any]]:
    """Get one launch area by key."""
    key = str(area_key or "").strip().lower().replace(" ", "_")
    if not key:
        return None
    for a in _load_config():
        if str(a.get("area_key") or "").strip().lower().replace(" ", "_") == key:
            return dict(a)
    return None


def is_place_in_launch_area(
    lat: float,
    lng: float,
    area_key: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Check if (lat, lng) falls within a launch area.
    If area_key given, check only that area. Else check all and return first match.
    Returns the matching area dict or None.
    """
    lat_f = _safe_float(lat, 0.0)
    lng_f = _safe_float(lng, 0.0)
    if not math.isfinite(lat_f) or not math.isfinite(lng_f):
        return None

    areas = _load_config()
    if area_key:
        key = str(area_key or "").strip().lower().replace(" ", "_")
        areas = [a for a in areas if str(a.get("area_key") or "").strip().lower().replace(" ", "_") == key]

    for a in areas:
        if not a.get("enabled", True):
            continue
        clat = _safe_float(a.get("center_lat"), 0.0)
        clng = _safe_float(a.get("center_lng"), 0.0)
        radius = _safe_float(a.get("radius_m"), _DEFAULT_RADIUS_M)
        if radius <= 0:
            radius = _DEFAULT_RADIUS_M
        # Haversine distance in meters
        phi1 = math.radians(lat_f)
        phi2 = math.radians(clat)
        dphi = math.radians(clat - lat_f)
        dlam = math.radians(clng - lng_f)
        a_val = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
        c = 2 * math.atan2(math.sqrt(a_val), math.sqrt(1 - a_val))
        dist_m = _EARTH_RADIUS_M * c
        if dist_m <= radius:
            return dict(a)
    return None


def sample_points_for_area(area_key: str, count: int = 5) -> List[Dict[str, Any]]:
    """Generate sample points around area center for readiness reports."""
    area = get_launch_area(area_key)
    if not area:
        return []
    clat = float(area.get("center_lat") or 0)
    clng = float(area.get("center_lng") or 0)
    radius = float(area.get("radius_m") or 1000)
    if not (-90 <= clat <= 90 and -180 <= clng <= 180):
        return []
    offset_deg = (radius / 1000.0) / 111.0 * 0.5
    points = [{"lat": clat, "lng": clng, "label": "center"}]
    if count >= 2:
        points.append({"lat": clat + offset_deg, "lng": clng, "label": "north"})
    if count >= 3:
        points.append({"lat": clat - offset_deg, "lng": clng, "label": "south"})
    if count >= 4:
        points.append({"lat": clat, "lng": clng + offset_deg * 0.9, "label": "east"})
    if count >= 5:
        points.append({"lat": clat, "lng": clng - offset_deg * 0.9, "label": "west"})
    return points[:count]


def get_area_for_place(place: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Get launch area for a place dict (uses lat/lng)."""
    lat = place.get("lat") or place.get("latitude")
    lng = place.get("lng") or place.get("longitude")
    if lat is None and "geometry" in place:
        loc = (place.get("geometry") or {}).get("location")
        if loc:
            lat = loc.get("lat")
            lng = loc.get("lng")
    return is_place_in_launch_area(lat or 0, lng or 0)
