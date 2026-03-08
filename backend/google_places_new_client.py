from __future__ import annotations

from typing import Any, Dict, List


DEFAULT_PLACES_NEARBY_URL = "https://places.googleapis.com/v1/places:searchNearby"

# Keep field mask minimal for Healthy Nearby cost/speed.
PLACES_NEARBY_FIELD_MASK_FIELDS = (
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "rating",
    "userRatingCount",
    "primaryType",
    "types",
    "businessStatus",
)
PLACES_NEARBY_FIELD_MASK = ",".join(f"places.{field}" for field in PLACES_NEARBY_FIELD_MASK_FIELDS)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def resolve_nearby_base(candidate_url: str | None) -> str:
    """Force Nearby Search (New) endpoint; reject legacy URL shapes."""
    url = str(candidate_url or "").strip()
    if url and "places.googleapis.com" in url and "places:searchNearby" in url:
        return url
    return DEFAULT_PLACES_NEARBY_URL


def build_nearby_search_payload(lat: float, lng: float, radius_m: int) -> Dict[str, Any]:
    # API allows up to 50; we keep 20 for speed and stable UI rendering.
    radius_val = float(max(200, min(5000, int(_safe_float(radius_m, 2000) or 2000))))
    return {
        "includedTypes": ["restaurant"],
        "maxResultCount": 20,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(_safe_float(lat, 0.0)),
                    "longitude": float(_safe_float(lng, 0.0)),
                },
                "radius": radius_val,
            }
        },
    }


def map_places_new_response(body: Dict[str, Any]) -> List[Dict[str, Any]]:
    places = body.get("places") if isinstance(body, dict) else []
    out: List[Dict[str, Any]] = []

    for item in (places or []):
        if not isinstance(item, dict):
            continue

        display_name = item.get("displayName") if isinstance(item.get("displayName"), dict) else {}
        location = item.get("location") if isinstance(item.get("location"), dict) else {}

        out.append(
            {
                # Keep legacy internal keys to avoid breaking current /places/healthy assembly.
                "name": str(display_name.get("text") or item.get("name") or "").strip(),
                "lat": float(_safe_float(location.get("latitude"), 0.0) or 0.0),
                "lng": float(_safe_float(location.get("longitude"), 0.0) or 0.0),
                "types": item.get("types") if isinstance(item.get("types"), list) else [],
                "vicinity": str(item.get("formattedAddress") or "").strip(),
                "rating": float(_safe_float(item.get("rating"), 0.0) or 0.0),
                "user_ratings_total": int(_safe_float(item.get("userRatingCount"), 0) or 0),
                # Optional extra fields from Places API (New), safe for future use.
                "place_id": str(item.get("id") or "").strip(),
                "primary_type": str(item.get("primaryType") or "").strip(),
                "business_status": str(item.get("businessStatus") or "").strip(),
            }
        )

    return out
