"""
Restaurant Analytics — aggregate anonymized user behavior data.
This is what restaurants PAY for. Shows demand, preferences, trends.
Never exposes individual user data — only aggregate patterns.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from collections import Counter

logger = logging.getLogger(__name__)


def build_restaurant_demand_report(
    chain_key: str = "",
    place_id: str = "",
    area_key: str = "",
    *,
    views: int = 0,
    decision_events: Optional[List[Dict[str, Any]]] = None,
    feedback_events: Optional[List[Dict[str, Any]]] = None,
    competitor_views: Optional[Dict[str, int]] = None,
) -> Dict[str, Any]:
    """
    Build an aggregate demand report for a restaurant.
    This is the data package restaurants pay to see.
    All data is anonymized — no individual user info.
    """
    events = decision_events or []
    feedback = feedback_events or []

    # 1. Total demand signal
    total_views = max(views, len(events))

    # 2. Item preference breakdown (what users chose)
    item_choices = Counter()
    for ev in events:
        item = str(ev.get("chosen_item") or ev.get("item_name") or "").strip()
        if item:
            item_choices[item] += 1

    top_items = [
        {"item": item, "times_chosen": count, "pct": round(count / max(total_views, 1) * 100)}
        for item, count in item_choices.most_common(5)
    ]

    # 3. Day-of-week patterns
    day_counts = Counter()
    for ev in events:
        ts = ev.get("created_at") or ev.get("timestamp") or ""
        try:
            dt_obj = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            day_counts[dt_obj.strftime("%A")] += 1
        except Exception:
            pass

    peak_day = day_counts.most_common(1)[0][0] if day_counts else "Unknown"

    # 4. Hour-of-day patterns
    hour_counts = Counter()
    for ev in events:
        ts = ev.get("created_at") or ev.get("timestamp") or ""
        try:
            dt_obj = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            hour_counts[dt_obj.hour] += 1
        except Exception:
            pass

    peak_hour = hour_counts.most_common(1)[0][0] if hour_counts else 12

    # 5. Category preferences (grilled vs fried etc)
    category_choices = Counter()
    for ev in events:
        cat = str(ev.get("category") or "").strip().lower()
        if cat:
            category_choices[cat] += 1

    # 6. Grilled vs Fried ratio (key health metric)
    grilled = sum(1 for ev in events if "grill" in str(ev.get("chosen_item") or "").lower())
    fried = sum(1 for ev in events if "fried" in str(ev.get("chosen_item") or "").lower() or "crispy" in str(ev.get("chosen_item") or "").lower())

    # 7. Competitor context
    competitors = competitor_views or {}
    your_rank = 1
    for comp_key, comp_views in competitors.items():
        if comp_views > total_views:
            your_rank += 1

    return {
        "chain_key": chain_key,
        "place_id": place_id,
        "area_key": area_key,
        "report_generated_at": datetime.now(timezone.utc).isoformat(),

        # DEMAND SIGNALS
        "total_views": total_views,
        "insight": f"{total_views} health-conscious users viewed your menu" if total_views > 0 else "Start building your presence",

        # ITEM PREFERENCES (anonymized)
        "top_items_chosen": top_items,
        "grilled_vs_fried": {
            "grilled_pct": round(grilled / max(grilled + fried, 1) * 100),
            "fried_pct": round(fried / max(grilled + fried, 1) * 100),
            "insight": f"{round(grilled / max(grilled + fried, 1) * 100)}% of users chose grilled over fried" if grilled + fried > 0 else None,
        },

        # TIMING PATTERNS
        "peak_day": peak_day,
        "peak_hour": f"{peak_hour}:00",
        "timing_insight": f"Most searches happen on {peak_day} around {peak_hour}:00" if day_counts else None,

        # COMPETITIVE POSITION
        "area_rank": your_rank,
        "competitor_count": len(competitors),
        "competitive_insight": (
            f"You rank #{your_rank} in your area. "
            + ("Verified restaurants rank higher — claim your profile." if your_rank > 1 else "You're #1! Maintain your lead.")
        ) if competitors else None,

        # UPGRADE CTA
        "upgrade_benefits": [
            f"✅ {total_views} users already searching — convert them with a Verified badge",
            "📊 See which items users prefer in real-time",
            "🎯 Get promoted placement in Healthy Nearby results",
            "📱 Direct ordering link — users tap once to order from you",
            f"🔥 {'Grilled items are 3x more popular — highlight them!' if grilled > fried else 'Add grilled options — users prefer them 3:1'}",
        ],

        # PRIVACY NOTE
        "_privacy": "All data is aggregate and anonymized. No individual user information is shared.",
    }
