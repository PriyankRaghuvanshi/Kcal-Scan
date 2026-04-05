"""
Deterministic decomposition of vision meal labels into ingredient-style parts.
Used to match clarification rules (e.g. oatmeal) even when the full label is
"Bowl with oatmeal and berries" and to scope user memory per component.
"""

from __future__ import annotations

import re
from typing import List, Set

_STOPWORDS: Set[str] = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "with",
    "some",
    "fresh",
    "hot",
    "cold",
    "small",
    "medium",
    "large",
    "of",
    "for",
    "my",
    "our",
    "your",
    "homemade",
    "side",
    "cup",
    "bowl",
    "plate",
    "serving",
}


def decompose_meal_label(name: str, *, max_parts: int = 12) -> List[str]:
    """
    Split a single vision line into candidate ingredient phrases (lowercase).
    No LLM — regex/split only. Order: full phrase first is handled by caller.
    """
    raw = str(name or "").strip()
    if not raw:
        return []
    lower = " ".join(raw.lower().split())
    chunks = [lower]

    for sep in (
        r"\s+with\s+",
        r"\s+and\s+",
        r",\s*",
        r";\s*",
        r"\s*/\s+",
        r"\s+/\s+",
        r"\s+\+\s*",
        r"\s*-\s*",
    ):
        nxt: List[str] = []
        for ch in chunks:
            parts = re.split(sep, ch, flags=re.I)
            for p in parts:
                t = p.strip(" \t-.,;+|/")
                if t:
                    nxt.append(t)
        chunks = nxt

    out: List[str] = []
    seen: Set[str] = set()
    for ch in chunks:
        words = [w for w in re.split(r"\s+", ch) if w and w not in _STOPWORDS]
        if not words:
            continue
        cleaned = " ".join(words).strip(" -.,;")
        if len(cleaned) < 3:
            continue
        if cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
        if len(out) >= max_parts:
            break
    return out


def clarification_phrases_for_item_name(name: str) -> List[str]:
    """Ordered phrases: full normalized label, then decomposed parts (unique)."""
    raw = str(name or "").strip()
    if not raw:
        return []
    full = " ".join(raw.lower().split())
    phrases: List[str] = []
    seen: Set[str] = set()
    for p in [full, *decompose_meal_label(raw)]:
        k = p.strip().lower()
        if not k or k in seen:
            continue
        seen.add(k)
        phrases.append(k)
    return phrases
