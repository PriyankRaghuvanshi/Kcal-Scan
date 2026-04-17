"""
Restaurant Profiles — the feature that makes restaurants come to US.

Every restaurant gets a public profile with:
- Health score
- Most popular healthy picks
- View count (how many CalorieClick users looked at this restaurant)
- Verified badge (restaurant claimed and uploaded official menu)
- Ranking position in their area

This is the Zomato play for health-conscious users:
List restaurants → users come → restaurants notice → restaurants pay for visibility.
"""
from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, Optional, List
from collections import Counter

logger = logging.getLogger(__name__)

_PROFILE_STORE_PATH = Path(__file__).resolve().parent / "data" / "restaurant_profiles.json"
_VIEW_COUNTS: Dict[str, int] = {}
_VIEW_LOCK = threading.Lock()


def track_restaurant_view(place_id: str, chain_key: str = "", place_name: str = ""):
    """Track every time a user views a restaurant in Healthy Nearby."""
    key = str(place_id or chain_key or "").strip()
    if not key:
        return
    with _VIEW_LOCK:
        _VIEW_COUNTS[key] = _VIEW_COUNTS.get(key, 0) + 1


def get_restaurant_view_count(place_id: str) -> int:
    """Get total views for a restaurant."""
    return _VIEW_COUNTS.get(str(place_id or "").strip(), 0)


def get_top_viewed_restaurants(limit: int = 20) -> List[Dict[str, Any]]:
    """Get most viewed restaurants — shows restaurants where demand exists."""
    sorted_views = sorted(_VIEW_COUNTS.items(), key=lambda x: -x[1])[:limit]
    return [{"place_id": pid, "views": count} for pid, count in sorted_views]


def build_restaurant_profile(
    place_id: str,
    place_name: str = "",
    chain_key: str = "",
    health_score: float = 0,
    best_item_name: str = "",
    best_item_calories: float = 0,
    best_item_protein: float = 0,
    menu_items: List[Dict[str, Any]] = None,
    is_verified: bool = False,
) -> Dict[str, Any]:
    """
    Build a public restaurant profile.
    This is what restaurants see when they search for themselves.
    """
    views = get_restaurant_view_count(place_id or chain_key)
    items = menu_items or []
    real_menu_count = sum(1 for it in items if it.get("menu_item_source") == "real_menu")

    # Health insights
    avg_cal = 0
    avg_protein = 0
    if items:
        cals = [float(it.get("estimated_calories") or 0) for it in items if it.get("estimated_calories")]
        pros = [float(it.get("estimated_protein_g") or 0) for it in items if it.get("estimated_protein_g")]
        avg_cal = round(sum(cals) / len(cals)) if cals else 0
        avg_protein = round(sum(pros) / len(pros), 1) if pros else 0

    # Top healthy picks (sorted by protein density)
    top_picks = sorted(
        [it for it in items if it.get("estimated_calories") and it.get("estimated_protein_g")],
        key=lambda x: float(x.get("estimated_protein_g", 0)) / max(float(x.get("estimated_calories", 1)), 1),
        reverse=True,
    )[:5]

    return {
        "place_id": place_id,
        "place_name": place_name,
        "chain_key": chain_key,
        "health_score": round(health_score),
        "views_count": views,
        "is_verified": is_verified,
        "verification_badge": "✅ Verified Menu" if is_verified else "📊 Community Data",
        "menu_item_count": len(items),
        "real_menu_count": real_menu_count,
        "avg_calories": avg_cal,
        "avg_protein_g": avg_protein,
        "best_pick": {
            "item_name": best_item_name,
            "calories": round(best_item_calories),
            "protein_g": round(best_item_protein, 1),
        } if best_item_name else None,
        "top_healthy_picks": [
            {
                "item_name": it.get("item_name"),
                "calories": round(float(it.get("estimated_calories", 0))),
                "protein_g": round(float(it.get("estimated_protein_g", 0)), 1),
                "protein_density": round(
                    float(it.get("estimated_protein_g", 0)) / max(float(it.get("estimated_calories", 1)), 1) * 100, 1
                ),
            }
            for it in top_picks
        ],
        "claim_cta": f"Own {place_name or 'this restaurant'}? Claim your profile to update menu + boost ranking.",
        "profile_url": f"/restaurant/{chain_key or place_id}",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def get_restaurant_analytics(chain_key: str) -> Dict[str, Any]:
    """
    Analytics for restaurant owners who claim their profile.
    Shows them WHY they should care about CalorieClick.
    """
    views = get_restaurant_view_count(chain_key)
    return {
        "chain_key": chain_key,
        "total_views": views,
        "insight": f"{views} CalorieClick users viewed your menu" if views > 0 else "Start building your presence",
        "recommendation": (
            "Your competitors are already on CalorieClick. Verify your menu to rank higher."
            if views > 10
            else "Claim your profile to appear in health-conscious searches."
        ),
        "upgrade_benefits": [
            "✅ Verified badge — ranks above unverified competitors",
            "📊 Real-time analytics — see how many users view your menu",
            "🎯 Promoted placement — appear first in Healthy Nearby",
            "📱 Direct ordering link — users order from you in one tap",
        ],
    }
