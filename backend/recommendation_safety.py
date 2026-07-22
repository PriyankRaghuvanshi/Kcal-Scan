from __future__ import annotations

from typing import Any, Dict, Tuple

_CHAIN_BACKED_MENU_SOURCES = frozenset(
    {
        "chain_registry",
        "ingested_chain_item",
    }
)


# Sources whose macros are trustworthy enough to label "verified" (real menu
# item, high confidence). Anything else that still passes the use_menu_order
# gate is "estimated"; a False gate is always "unknown".
_VERIFIED_NUTRITION_SOURCES = frozenset(
    {
        "real_menu",
        "user_scan",
        "menu_intelligence_store",
        "structured_menu",
        "chain_registry",
        "ingested_chain_item",
        "exact_menu_cache",
    }
)

_VERIFIED_NUTRITION_PROVENANCE = frozenset({"exact_chain_menu", "exact_menu"})


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


def should_use_honest_no_menu_order_copy(
    *,
    strong_menu_evidence: bool,
    menu_item_source: Any,
    menu_item_confidence: Any,
) -> bool:
    """
    When true, replace cuisine-rule dish names with honest pattern copy so we do not
    imply a specific menu item exists (trust / AI perception).
    """
    if strong_menu_evidence:
        return False
    src = _norm_text(menu_item_source)
    conf = _safe_float(menu_item_confidence, 0.0)
    if src in _CHAIN_BACKED_MENU_SOURCES and conf >= 0.55:
        return False
    return True


def compute_nutrition_status(
    *,
    use_menu_order: bool,
    menu_item_source: Any,
    menu_item_confidence: Any,
    item_provenance: Any = "",
) -> str:
    """
    Three-value evidence gate for whether a venue's macros are real.

    - "verified": a real, high-confidence menu item backs the numbers.
    - "estimated": use_menu_order passed but below the verified bar (inference)
      — numbers still come from a real named menu item, labeled estimate.
    - "unknown": no real menu item backs the numbers (cuisine tables, 520/32,
      generic "Lighter menu option", honest-copy path) — macros MUST be nulled.

    Hangs off the ALREADY-COMPUTED use_menu_order gate; a False gate is always
    "unknown". A per-cuisine bucket lookup is "unknown", never "estimated".
    """
    if not use_menu_order:
        return "unknown"
    prov = _norm_text(item_provenance)
    if prov in _VERIFIED_NUTRITION_PROVENANCE:
        return "verified"
    src = _norm_text(menu_item_source)
    conf = _safe_float(menu_item_confidence, 0.0)
    if src in _VERIFIED_NUTRITION_SOURCES and conf >= 0.72:
        return "verified"
    return "estimated"


def honest_no_menu_order_copy(context_text: Any) -> Tuple[str, str]:
    """
    Short user-facing order line + label when we only have venue/cuisine heuristics.
    Always includes 'no menu on file' so meal_ranking treats this as generic fallback.
    """
    ctx = _norm_text(context_text)
    suffix = " (typical pattern — no menu on file)"
    if any(token in ctx for token in _SOUTH_INDIAN_TOKENS):
        return (f"Steamed idli or plain dosa if they offer it{suffix}", "No menu on file")
    if any(token in ctx for token in _INDIAN_TOKENS):
        return (
            f"Grilled/tandoori protein + lentil sides; go easy on creamy curries{suffix}",
            "No menu on file",
        )
    if any(token in ctx for token in _DESSERT_TOKENS):
        return (f"Savory lighter plates over desserts/pastries{suffix}", "No menu on file")
    if any(token in ctx for token in _CAFE_TOKENS):
        return (f"Eggs, yogurt, or a simple sandwich — not a pastry drink combo{suffix}", "No menu on file")
    if any(token in ctx for token in ("sushi", "japanese", "ramen", "sashimi", "teriyaki")):
        return (f"Sashimi or grilled items; lighter on fried rolls and mayo{suffix}", "No menu on file")
    if any(token in ctx for token in ("mexican", "burrito", "taco", "quesadilla", "chipotle")):
        return (f"Protein bowl or soft tacos; skip loaded nachos/queso{suffix}", "No menu on file")
    if any(token in ctx for token in ("thai", "chinese", "noodle", "wok", "stir fry")):
        return (f"Lean protein stir-fry; lighter sauce and controlled rice/noodles{suffix}", "No menu on file")
    if any(token in ctx for token in ("pizza", "pizzeria")):
        return (f"Thin-crust + protein toppings; small portion + side salad{suffix}", "No menu on file")
    if any(
        token in ctx
        for token in (
            "burger",
            "fast_food",
            "fast food",
            "fried chicken",
            "wings",
            "subway",
            "sub sandwich",
            "sandwich",
        )
    ):
        return (
            f"Single grilled chicken or turkey portion + salad; skip fries and sugary drinks{suffix}",
            "No menu on file",
        )
    if any(token in ctx for token in ("grill", "bbq", "kebab", "rotisserie")):
        return (f"Grilled meat/fish + vegetables or salad{suffix}", "No menu on file")
    if any(token in ctx for token in ("salad", "bowl", "poke", "healthy")):
        return (f"Protein-forward bowl or salad; dressing on the side{suffix}", "No menu on file")
    return (f"Grilled or baked protein with vegetables or salad{suffix}", "No menu on file")
