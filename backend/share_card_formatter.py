from __future__ import annotations

from typing import Any, Dict, Iterable, List


SHARE_CARD_TITLE = "Best Order Near Me"
SHARE_CARD_VERSION = "v1"


_TAG_TO_BADGE: Dict[str, str] = {
    "high_protein": "High Protein",
    "fat_loss_friendly": "Fat Loss Friendly",
    "cut_friendly": "Fat Loss Friendly",
    "cut_mode": "Cut Mode",
    "calorie_control": "Calorie Control",
    "lower_calorie": "Calorie Control",
    "high_satiety": "Filling Pick",
    "better_swap": "Smart Swap",
}


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _clip(text: Any, max_len: int, fallback: str) -> str:
    value = str(text or "").strip()
    if not value:
        value = fallback
    if len(value) <= max_len:
        return value
    return value[: max(0, max_len - 1)].rstrip() + "…"


def _score_to_100(health_score: Any) -> int:
    try:
        value = float(health_score)
    except Exception:
        value = 0.0

    # Existing place score is 1-10; share card uses social-friendly 0-100.
    if value <= 10.0:
        value *= 10.0

    return int(round(_clamp(value, 0.0, 100.0)))


def _build_badges(
    recommended_badges: Iterable[Any],
    order_strategy_tags: Iterable[Any],
    cut_friendly: bool,
    fat_loss_friendly: bool,
) -> List[str]:
    badges: List[str] = []

    if cut_friendly or fat_loss_friendly:
        badges.append("Fat Loss Friendly")

    for raw in recommended_badges:
        label = str(raw or "").strip()
        if not label:
            continue

        lower = label.lower()
        if "high-protein" in lower or "high protein" in lower:
            badges.append("High Protein")
        elif "calorie" in lower:
            badges.append("Calorie Control")
        elif "satiety" in lower:
            badges.append("Filling Pick")

    for tag in order_strategy_tags:
        label = _TAG_TO_BADGE.get(str(tag or "").strip().lower())
        if label:
            badges.append(label)

    deduped: List[str] = []
    seen = set()
    for badge in badges:
        if badge in seen:
            continue
        seen.add(badge)
        deduped.append(_clip(badge, 24, "Badge"))

    if not deduped:
        deduped = ["Smart Choice"]

    return deduped[:4]


def build_best_order_share_card(
    *,
    place_name: Any,
    health_score: Any,
    best_order: Any,
    estimated_calories: Any,
    estimated_protein_g: Any,
    subtitle: Any,
    recommended_badges: Iterable[Any] | None = None,
    order_strategy_tags: Iterable[Any] | None = None,
    cut_friendly: bool = False,
    fat_loss_friendly: bool = False,
) -> Dict[str, Any]:
    try:
        calories = int(round(float(estimated_calories)))
    except Exception:
        calories = 520

    try:
        protein = int(round(float(estimated_protein_g)))
    except Exception:
        protein = 32

    safe_subtitle = _clip(
        subtitle,
        88,
        "High protein and better calorie control for your cut.",
    )

    return {
        "title": SHARE_CARD_TITLE,
        "place_name": _clip(place_name, 40, "Nearby Pick"),
        "health_score": _score_to_100(health_score),
        "best_order": _clip(best_order, 64, "Grilled protein bowl"),
        "estimated_calories": max(0, calories),
        "estimated_protein_g": max(0, protein),
        "subtitle": safe_subtitle,
        "badges": _build_badges(
            recommended_badges or [],
            order_strategy_tags or [],
            cut_friendly=bool(cut_friendly),
            fat_loss_friendly=bool(fat_loss_friendly),
        ),
        "share_card_version": SHARE_CARD_VERSION,
    }
