from __future__ import annotations

from typing import Any, Dict


_GENERIC_BANNED_ITEM_TOKENS = (
    "greek yogurt protein bowl",
    "grilled protein bowl",
    "protein bowl",
    "protein plate",
    "lean wrap",
)

_SOUTH_INDIAN_TOKENS = (
    "south indian",
    "udupi",
    "idli",
    "dosa",
    "sambar",
    "temple",
    "canteen",
)

_INDIAN_TOKENS = (
    "indian",
    "biryani",
    "tandoori",
    "dal",
    "paneer",
    "curry",
)

_DESSERT_TOKENS = (
    "patisserie",
    "pastry",
    "dessert",
    "sweet",
    "cake",
    "ice cream",
    "bakery",
)

_CAFE_TOKENS = (
    "cafe",
    "coffee",
    "brunch",
)


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _coarse_fallback_name(context_text: str) -> str:
    text = _norm_text(context_text)
    if any(token in text for token in _SOUTH_INDIAN_TOKENS):
        return "Idli or plain dosa-style option"
    if any(token in text for token in _INDIAN_TOKENS):
        return "Tandoori or grilled style option"
    if any(token in text for token in _DESSERT_TOKENS):
        return "Needs menu check: choose lighter savory options"
    if any(token in text for token in _CAFE_TOKENS):
        return "Egg, yogurt, or sandwich-style lighter option"
    return "Suggested lighter option"


def _is_cuisine_sensitive_context(context_text: str) -> bool:
    text = _norm_text(context_text)
    return bool(
        any(token in text for token in _INDIAN_TOKENS)
        or any(token in text for token in _SOUTH_INDIAN_TOKENS)
        or any(token in text for token in _DESSERT_TOKENS)
        or any(token in text for token in _CAFE_TOKENS)
    )


def _is_banned_generic_name(item_name: Any) -> bool:
    text = _norm_text(item_name)
    return bool(text and any(token in text for token in _GENERIC_BANNED_ITEM_TOKENS))


def has_strong_menu_evidence(
    *,
    menu_item_source: str,
    menu_item_confidence: Any,
    source_url: Any = "",
    extraction_method: Any = "",
    parse_method: Any = "",
    raw_text_snippet: Any = "",
) -> bool:
    source = _norm_text(menu_item_source)
    confidence = _safe_float(menu_item_confidence, 0.0)
    extraction = _norm_text(extraction_method)
    parse = _norm_text(parse_method)
    snippet = _norm_text(raw_text_snippet)
    has_url = bool(str(source_url or "").strip())

    if source == "user_scan":
        return bool(confidence >= 0.72 and (has_url or len(snippet) >= 8))

    if source != "real_menu":
        return False

    extraction_ok = extraction in {
        "menu_link_fetch",
        "website_menu_fetch",
        "menu_scrape",
        "ocr_menu",
        "user_scan_ocr",
        "review_text_extract",
    }
    parse_ok = parse in {"deterministic", "llm_inferred", "llm"}
    snippet_ok = len(snippet) >= 8
    return bool(confidence >= 0.82 and (has_url or extraction_ok or parse_ok or snippet_ok))


def sanitize_recommended_item(
    *,
    item_name: Any,
    context_text: Any,
    menu_item_source: Any,
    menu_item_confidence: Any,
    strong_menu_evidence: bool,
    display_label: Any = "",
    order_type: Any = "",
) -> Dict[str, Any]:
    resolved_name = str(item_name or "").strip()
    source = _norm_text(menu_item_source) or "heuristic"
    confidence = max(0.2, min(0.97, _safe_float(menu_item_confidence, 0.45)))
    label = str(display_label or "").strip()
    resolved_order_type = str(order_type or "").strip().lower()
    ctx = _norm_text(context_text)

    if not resolved_name:
        return {
            "item_name": _coarse_fallback_name(ctx),
            "menu_item_source": "heuristic",
            "menu_item_confidence": round(min(confidence, 0.45), 2),
            "display_label": "Needs Menu Check",
            "order_type": "estimated",
            "sanitized": True,
            "safety_reason": "empty_item_name",
        }

    if not _is_banned_generic_name(resolved_name) or not _is_cuisine_sensitive_context(ctx):
        return {
            "item_name": resolved_name,
            "menu_item_source": source,
            "menu_item_confidence": round(confidence, 2),
            "display_label": label,
            "order_type": resolved_order_type if resolved_order_type in {"exact", "likely", "estimated"} else "",
            "sanitized": False,
            "safety_reason": "",
        }

    if source == "real_menu" and strong_menu_evidence:
        return {
            "item_name": resolved_name,
            "menu_item_source": source,
            "menu_item_confidence": round(confidence, 2),
            "display_label": label,
            "order_type": resolved_order_type if resolved_order_type in {"exact", "likely", "estimated"} else "",
            "sanitized": False,
            "safety_reason": "",
        }

    return {
        "item_name": _coarse_fallback_name(ctx),
        "menu_item_source": "heuristic" if source == "real_menu" else source,
        "menu_item_confidence": round(min(confidence, 0.54), 2),
        "display_label": "Needs Menu Check" if confidence < 0.5 else "Suggested Lighter Option",
        "order_type": "estimated",
        "sanitized": True,
        "safety_reason": "cuisine_guardrail_generic_fallback_blocked",
    }
