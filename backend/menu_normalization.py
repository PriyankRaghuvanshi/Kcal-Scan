"""
Deterministic menu normalization.

Goal: take menu-like candidates from different sources (real menu, chain registry,
menu inference, cuisine heuristics) and normalize them into a comparable shape.
No ranking and no LLM/web scraping here.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List


_SPACE_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s\-/&+]")


def normalize_item_name(name: Any) -> str:
    raw = str(name or "").strip()
    if not raw:
        return ""
    cleaned = _PUNCT_RE.sub(" ", raw)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def infer_category(item_name: str) -> str:
    text = str(item_name or "").strip().lower()
    if any(t in text for t in ("smoothie", "juice", "acai", "shake")):
        return "drink"
    if any(t in text for t in ("salad", "bowl", "plate")):
        return "bowl"
    if any(t in text for t in ("wrap", "sub", "sandwich", "burger")):
        return "sandwich"
    if "pizza" in text or "slice" in text:
        return "pizza"
    if any(t in text for t in ("dosa", "idli", "sambar", "uthappam")):
        return "south_indian"
    if any(t in text for t in ("tandoori", "tikka", "dal", "paneer", "roti", "naan", "curry")):
        return "indian"
    if any(t in text for t in ("coffee", "espresso", "latte")):
        return "coffee"
    return "meal"


def detect_negative_flags(item_name: str) -> List[str]:
    text = str(item_name or "").strip().lower()
    flags: List[str] = []
    if any(t in text for t in ("combo", "meal deal", "with fries", "fries +", "family")):
        flags.append("combo")
    if any(t in text for t in ("fried", "deep fried", "crispy", "tempura")):
        flags.append("fried")
    if any(t in text for t in ("shake", "soda", "cola", "sweet", "dessert", "pastry", "cake", "ice cream")):
        flags.append("sugar")
    if any(t in text for t in ("creamy", "butter", "alfredo", "mayo", "cheesy", "stuffed crust")):
        flags.append("heavy_sauce")
    return flags


def supports_swaps_for_item(item_name: str, category: str) -> bool:
    text = str(item_name or "").strip().lower()
    if category in {"pizza", "sandwich", "bowl", "meal", "indian", "south_indian"}:
        return True
    if any(t in text for t in ("wrap", "sub", "sandwich", "pizza", "bowl", "salad", "curry", "dosa", "idli")):
        return True
    return False


def normalize_menu_candidates(
    place: Dict[str, Any],
    raw_items: List[Dict[str, Any]],
    *,
    default_source: str = "heuristic",
    default_confidence: float = 0.52,
) -> List[Dict[str, Any]]:
    """
    Normalize a list of raw menu candidate dicts to a standard shape.
    Keeps unknown fields, but ensures item_name/calories/protein/source/confidence/tags are present.
    """
    out: List[Dict[str, Any]] = []
    for row in raw_items or []:
        if not isinstance(row, dict):
            continue
        item_name = normalize_item_name(row.get("item_name") or row.get("name"))
        if not item_name:
            continue
        calories = row.get("estimated_calories") or row.get("calories") or 0
        protein = row.get("estimated_protein_g") or row.get("protein_g") or 0
        try:
            calories_i = int(round(float(calories)))
        except Exception:
            calories_i = 0
        try:
            protein_i = int(round(float(protein)))
        except Exception:
            protein_i = 0
        source = str(row.get("menu_item_source") or row.get("source") or default_source).strip().lower() or default_source
        try:
            conf = float(row.get("menu_item_confidence") or row.get("confidence") or default_confidence)
        except Exception:
            conf = float(default_confidence)
        conf = max(0.2, min(0.97, conf))
        category = str(row.get("category") or infer_category(item_name)).strip()
        negative_flags = row.get("negative_flags") if isinstance(row.get("negative_flags"), list) else detect_negative_flags(item_name)
        tags = row.get("tags") if isinstance(row.get("tags"), list) else []
        supports_swaps = bool(row.get("supports_swaps")) if row.get("supports_swaps") is not None else supports_swaps_for_item(item_name, category)

        normalized = dict(row)
        normalized.update(
            {
                "item_name": item_name,
                "estimated_calories": calories_i if calories_i > 0 else int(row.get("estimated_calories") or 0),
                "estimated_protein_g": protein_i if protein_i > 0 else int(row.get("estimated_protein_g") or 0),
                "category": category,
                "menu_item_source": source,
                "menu_item_confidence": round(conf, 2),
                "tags": tags,
                "supports_swaps": supports_swaps,
                "negative_flags": negative_flags,
            }
        )
        out.append(normalized)
    return out

