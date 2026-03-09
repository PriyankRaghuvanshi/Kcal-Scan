from __future__ import annotations

import re
from typing import Any, Iterable, List


_PUNCT_RE = re.compile(r"[^\w\s\-/&+]")
_SPACE_RE = re.compile(r"\s+")


def _norm(text: Any) -> str:
    raw = str(text or "").strip().lower()
    if not raw:
        return ""
    cleaned = _PUNCT_RE.sub(" ", raw)
    cleaned = _SPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _clip(text: str, max_len: int = 52) -> str:
    value = str(text or "").strip()
    if len(value) <= max_len:
        return value
    return value[: max(0, max_len - 1)].rstrip() + "…"


def _capitalize_phrase(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    return value[0].upper() + value[1:]


def _to_skip_phrase(item: Any) -> str:
    token = _norm(item)
    if not token:
        return ""
    if token.startswith("skip "):
        return _capitalize_phrase(token)
    if " and " in token and token.startswith("fries"):
        return "Skip fries and sugary drinks"
    return _clip(_capitalize_phrase(f"Skip {token}"))


def _to_add_phrase(item: Any) -> str:
    token = _norm(item)
    if not token:
        return ""
    if token.startswith(("add ", "choose ", "pick ", "go for ")):
        return _clip(_capitalize_phrase(token))
    if "water" in token or "zero-sugar" in token or "zero sugar" in token:
        return "Choose water or zero-sugar drink"
    return _clip(_capitalize_phrase(f"Add {token}"))


def _parse_swap_suggestion(swap_suggestion: str) -> List[str]:
    text = str(swap_suggestion or "").strip()
    if not text:
        return []

    lowered = text.lower()
    out: List[str] = []
    if lowered.startswith("skip ") and ", add " in lowered:
        head, tail = text.split(",", 1)
        out.append(_capitalize_phrase(head.strip()))
        out.append(_capitalize_phrase(tail.strip()))
        return [x for x in out if x]

    if lowered.startswith(("skip ", "choose ", "pick ", "go for ", "add ")):
        return [_clip(_capitalize_phrase(text))]

    # fallback for free-form sentence
    return [_clip(_capitalize_phrase(text))]


def _fallback_for_context(place_text: str, low_confidence: bool) -> List[str]:
    text = _norm(place_text)

    if any(token in text for token in ("subway", "sandwich", "sub ")):
        return ["Skip mayo", "Add extra salad", "Choose water or zero-sugar drink"]
    if any(token in text for token in ("nando", "grill", "bbq", "rotisserie")):
        return ["Swap chips for salad", "Skip creamy sauces", "Choose zero-sugar drink"]
    if any(token in text for token in ("burger", "hungry jack", "mcd", "fast food", "fast_food")):
        return ["Skip fries", "Choose zero-sugar drink", "Keep sauces light"]
    if any(token in text for token in ("indian", "south indian", "biryani", "temple", "canteen")):
        if low_confidence:
            return ["Prefer lighter, less oily dishes", "Skip fried or creamy extras"]
        return ["Skip naan or fried extras", "Choose tandoori or dal-style option", "Keep oil-heavy sides light"]
    if any(token in text for token in ("patisserie", "dessert", "pastry", "bakery")):
        return ["Choose a smaller serve", "Skip sweet drinks"]
    if any(token in text for token in ("cafe", "coffee")):
        return ["Skip pastry extras", "Choose no-sugar drink", "Add a lean protein side"]
    if low_confidence:
        return ["Prefer lighter sauces", "Skip calorie-dense extras"]
    return ["Skip calorie-dense extras", "Add vegetables or lean protein"]


def build_swap_suggestions(
    *,
    swap_suggestion: Any = "",
    skip_items: Iterable[Any] | None = None,
    add_items: Iterable[Any] | None = None,
    better_swap: Any = "",
    place_context: Any = "",
    menu_item_source: Any = "",
    menu_item_confidence: Any = None,
    max_items: int = 3,
) -> List[str]:
    limit = max(1, min(3, int(max_items)))
    source = _norm(menu_item_source)
    try:
        conf = float(menu_item_confidence)
    except Exception:
        conf = 0.0
    conf = max(0.0, min(1.0, conf))
    low_confidence = source == "heuristic" or conf < 0.5

    out: List[str] = []

    for row in skip_items or []:
        phrase = _to_skip_phrase(row)
        if phrase:
            out.append(phrase)

    for row in add_items or []:
        phrase = _to_add_phrase(row)
        if phrase:
            out.append(phrase)

    for phrase in _parse_swap_suggestion(str(swap_suggestion or "")):
        if phrase:
            out.append(phrase)

    better = str(better_swap or "").strip()
    if better:
        out.append(_clip(_capitalize_phrase(better)))

    if not out:
        out.extend(_fallback_for_context(str(place_context or ""), low_confidence))

    deduped: List[str] = []
    seen = set()
    for row in out:
        value = _clip(str(row or "").strip())
        if not value:
            continue
        key = _norm(value)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(value)
        if len(deduped) >= limit:
            break

    return deduped

