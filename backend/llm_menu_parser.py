from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple

try:
    import google.generativeai as genai
except Exception:  # pragma: no cover - dependency can be unavailable in some test envs.
    genai = None  # type: ignore[assignment]


LLM_MENU_PARSE_VERSION = "v1"

_TRUE_VALUES = {"1", "true", "yes", "y", "on"}
_MAX_TEXT_CHARS = 7000

_ALLOWED_CATEGORIES = {
    "bowl",
    "salad",
    "burger",
    "wrap",
    "pizza",
    "sushi",
    "curry",
    "sandwich",
    "taco",
    "burrito",
    "combo",
    "drink",
    "dessert",
    "rice",
    "noodle",
    "plate",
    "other",
}

_ALLOWED_HEALTH_SIGNALS = {
    "high_protein",
    "lean_protein",
    "high_fiber",
    "fried",
    "deep_fried",
    "creamy_sauce",
    "sugary_drink",
    "calorie_dense",
}

_PROTEIN_HINTS = {
    "chicken": ("chicken", "tikka", "kebab", "shawarma", "nugget"),
    "beef": ("beef", "steak", "burger", "brisket"),
    "fish": ("fish", "salmon", "tuna", "sashimi", "prawn", "shrimp"),
    "pork": ("pork", "bacon", "ham"),
    "egg": ("egg", "omelette"),
    "tofu": ("tofu",),
    "paneer": ("paneer",),
    "lentil": ("lentil", "dal", "bean", "chickpea"),
}

_CARB_HINTS = (
    "rice",
    "bread",
    "naan",
    "pita",
    "wrap",
    "taco",
    "burrito",
    "pizza",
    "pasta",
    "noodle",
    "potato",
    "fries",
)

_FAT_HINTS = (
    "pesto",
    "mayo",
    "cheese",
    "cream",
    "butter",
    "aioli",
    "oil",
    "avocado",
    "nuts",
)

_CATEGORY_HINTS: List[Tuple[str, Tuple[str, ...]]] = [
    ("bowl", ("bowl", "grain bowl", "poke")),
    ("salad", ("salad",)),
    ("burger", ("burger",)),
    ("wrap", ("wrap", "roll")),
    ("pizza", ("pizza", "slice")),
    ("sushi", ("sushi", "sashimi", "nigiri")),
    ("curry", ("curry", "masala", "korma")),
    ("sandwich", ("sandwich",)),
    ("taco", ("taco",)),
    ("burrito", ("burrito",)),
    ("combo", ("combo", "meal", "bucket", "family")),
    ("drink", ("drink", "shake", "juice", "soda", "cola")),
    ("dessert", ("dessert", "cake", "ice cream", "brownie")),
    ("rice", ("rice",)),
    ("noodle", ("noodle", "ramen", "udon")),
    ("plate", ("plate", "platter")),
]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _normalized_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return _normalized_text(raw) in _TRUE_VALUES


def _menu_parser_model_name() -> str:
    return (
        str(os.getenv("MENU_PARSER_LLM_MODEL", "") or "").strip()
        or str(os.getenv("SCAN_LLM_MODEL", "") or "").strip()
        or str(os.getenv("GEMINI_MODEL", "") or "").strip()
        or "gemini-2.5-flash"
    )


def _menu_parser_timeout_sec() -> float:
    try:
        val = float(str(os.getenv("MENU_PARSER_LLM_TIMEOUT_SEC", "4") or "4").strip())
    except Exception:
        val = 4.0
    return _clamp(val, 2.0, 8.0)


def _llm_available() -> bool:
    return bool(genai is not None) and bool(str(os.getenv("GEMINI_API_KEY", "") or "").strip())


def _strip_fences(text: str) -> str:
    payload = str(text or "").strip()
    if payload.startswith("```json"):
        payload = payload[len("```json") :].strip()
    if payload.startswith("```"):
        payload = payload[len("```") :].strip()
    if payload.endswith("```"):
        payload = payload[:-3].strip()
    return payload


def _extract_json_payload(text: str) -> Any:
    payload = _strip_fences(text)
    if not payload:
        return None

    try:
        return json.loads(payload)
    except Exception:
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start >= 0 and end > start:
        snippet = payload[start : end + 1]
        try:
            return json.loads(snippet)
        except Exception:
            return None
    return None


def _coerce_list(value: Any, limit: int = 4) -> List[str]:
    if isinstance(value, list):
        raw = [str(x or "").strip() for x in value]
    else:
        text = str(value or "").strip()
        if not text:
            return []
        raw = [chunk.strip() for chunk in re.split(r"[,/;+]| and ", text) if chunk.strip()]

    out: List[str] = []
    seen = set()
    for row in raw:
        token = _normalized_text(row)
        if not token or token in seen:
            continue
        seen.add(token)
        out.append(token)
        if len(out) >= limit:
            break
    return out


def _infer_category(item_name: str) -> str:
    text = _normalized_text(item_name)
    for category, tokens in _CATEGORY_HINTS:
        if any(token in text for token in tokens):
            return category
    return "other"


def _infer_protein(item_name: str) -> str:
    text = _normalized_text(item_name)
    for protein, tokens in _PROTEIN_HINTS.items():
        if any(token in text for token in tokens):
            return protein
    return ""


def _infer_components(item_name: str) -> Tuple[List[str], List[str]]:
    text = _normalized_text(item_name)
    carbs = [token for token in _CARB_HINTS if token in text][:4]
    fats = [token for token in _FAT_HINTS if token in text][:4]
    return carbs, fats


def _normalize_signal(value: Any) -> str:
    token = _normalized_text(value).replace("-", "_").replace(" ", "_")
    if token in _ALLOWED_HEALTH_SIGNALS:
        return token
    return ""


def _infer_health_signals(
    item_name: str,
    *,
    likely_protein: str,
    carbs: List[str],
    fats: List[str],
    category: str,
) -> List[str]:
    text = _normalized_text(item_name)
    out: List[str] = []
    if likely_protein in {"chicken", "fish", "beef", "egg", "tofu", "paneer"}:
        out.append("high_protein")
        if likely_protein in {"chicken", "fish", "tofu", "egg"}:
            out.append("lean_protein")
    if "salad" in text or "bowl" in text:
        out.append("high_fiber")
    if any(token in text for token in ("fried", "crispy", "tempura")):
        out.append("fried")
        out.append("deep_fried")
    if any(token in text for token in ("cream", "creamy", "mayo", "aioli")):
        out.append("creamy_sauce")
    if category == "drink" and any(token in text for token in ("shake", "soda", "cola", "juice")):
        out.append("sugary_drink")
    if any(token in text for token in ("loaded", "double", "family", "bucket", "combo")):
        out.append("calorie_dense")
    if carbs and any(token in carbs for token in ("fries", "pizza")):
        out.append("calorie_dense")
    if fats and any(token in fats for token in ("cream", "mayo", "butter")):
        out.append("calorie_dense")
    deduped = []
    seen = set()
    for row in out:
        token = _normalize_signal(row)
        if token and token not in seen:
            seen.add(token)
            deduped.append(token)
    return deduped[:4]


def _sanitize_item(payload: Dict[str, Any], fallback_confidence: float = 0.62) -> Dict[str, Any] | None:
    row = payload if isinstance(payload, dict) else {}
    item_name = str(row.get("item_name") or row.get("name") or row.get("title") or "").strip()
    if not item_name:
        return None

    category = _normalized_text(row.get("category"))
    if category not in _ALLOWED_CATEGORIES:
        category = _infer_category(item_name)

    likely_protein = _normalized_text(row.get("likely_protein") or row.get("protein_source"))
    if not likely_protein:
        likely_protein = _infer_protein(item_name)

    likely_carbs = _coerce_list(row.get("likely_carbs"))
    likely_fats = _coerce_list(row.get("likely_fats"))
    if not likely_carbs or not likely_fats:
        inferred_carbs, inferred_fats = _infer_components(item_name)
        if not likely_carbs:
            likely_carbs = inferred_carbs
        if not likely_fats:
            likely_fats = inferred_fats

    health_signals_raw = _coerce_list(row.get("health_signals"), limit=6)
    health_signals: List[str] = []
    for raw_signal in health_signals_raw:
        normalized_signal = _normalize_signal(raw_signal)
        if normalized_signal:
            health_signals.append(normalized_signal)
    if not health_signals:
        health_signals = _infer_health_signals(
            item_name,
            likely_protein=likely_protein,
            carbs=likely_carbs,
            fats=likely_fats,
            category=category,
        )

    parser_confidence = _safe_float(
        row.get("parser_confidence", row.get("confidence")),
        fallback_confidence,
    )
    parser_confidence = round(_clamp(parser_confidence, 0.35, 0.98), 2)

    return {
        "item_name": item_name,
        "category": category,
        "likely_protein": likely_protein,
        "likely_carbs": likely_carbs[:4],
        "likely_fats": likely_fats[:4],
        "health_signals": health_signals[:5],
        "parser_confidence": parser_confidence,
    }


def _dedupe_items(items: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    seen: Dict[str, int] = {}
    for row in items:
        if not isinstance(row, dict):
            continue
        normalized = _normalized_text(row.get("item_name"))
        if not normalized:
            continue
        conf = _safe_float(row.get("parser_confidence"), 0.0)
        if normalized in seen:
            idx = seen[normalized]
            existing_conf = _safe_float(out[idx].get("parser_confidence"), 0.0)
            if conf > existing_conf:
                out[idx] = row
            continue
        seen[normalized] = len(out)
        out.append(row)
        if len(out) >= max_items:
            break
    return out


def _fallback_structured_items(
    deterministic_items: List[Dict[str, Any]],
    *,
    max_items: int,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in deterministic_items:
        if not isinstance(row, dict):
            continue
        item_name = str(row.get("item_name") or "").strip()
        if not item_name:
            continue
        fallback_conf = _safe_float(row.get("confidence"), 0.62)
        normalized = _sanitize_item({"item_name": item_name, "confidence": fallback_conf}, fallback_confidence=fallback_conf)
        if normalized:
            out.append(normalized)
    return _dedupe_items(out, max_items=max_items)


def _to_scoring_items(structured_items: List[Dict[str, Any]], max_items: int) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for row in structured_items[:max_items]:
        out.append(
            {
                "item_name": str(row.get("item_name") or "").strip(),
                "confidence": round(_clamp(_safe_float(row.get("parser_confidence"), 0.62), 0.2, 0.99), 2),
            }
        )
    return out


def _looks_messy_text(raw_text: str) -> bool:
    text = str(raw_text or "")
    if not text.strip():
        return False
    markers = ("|", "\t", "  ", ".....", "•", "combo", "special", "house", "chef")
    marker_hits = sum(text.lower().count(marker) for marker in markers)
    return marker_hits >= 4


def _should_try_llm(
    *,
    raw_text: str,
    ocr_lines: Optional[List[str]],
    deterministic_items: List[Dict[str, Any]],
) -> bool:
    item_count = len(deterministic_items)
    if item_count < 3:
        return True

    avg_conf = sum(_safe_float(x.get("confidence"), 0.55) for x in deterministic_items) / max(1, item_count)
    if avg_conf < 0.58:
        return True

    lines = [str(x or "") for x in (ocr_lines or []) if str(x or "").strip()]
    if not lines:
        lines = [row for row in str(raw_text or "").splitlines() if row.strip()]
    if lines:
        parse_density = float(item_count / max(1, len(lines)))
        if len(lines) >= 8 and parse_density < 0.40:
            return True

    return _looks_messy_text(raw_text)


def _build_llm_prompt(raw_text: str, ocr_lines: Optional[List[str]], max_items: int) -> str:
    lines = [str(x or "").strip() for x in (ocr_lines or []) if str(x or "").strip()]
    if not lines:
        lines = [row.strip() for row in str(raw_text or "").splitlines() if row.strip()]

    trimmed = "\n".join(lines[:140])[:_MAX_TEXT_CHARS]
    if not trimmed:
        trimmed = str(raw_text or "")[:_MAX_TEXT_CHARS]

    return (
        "You are a strict JSON extractor for restaurant menus.\n"
        "Return ONLY valid JSON with this exact top-level shape:\n"
        "{\n"
        '  "parsed_items": [\n'
        "    {\n"
        '      "item_name": "string",\n'
        '      "category": "bowl|salad|burger|wrap|pizza|sushi|curry|sandwich|taco|burrito|combo|drink|dessert|rice|noodle|plate|other",\n'
        '      "likely_protein": "string",\n'
        '      "likely_carbs": ["string"],\n'
        '      "likely_fats": ["string"],\n'
        '      "health_signals": ["high_protein|lean_protein|high_fiber|fried|deep_fried|creamy_sauce|sugary_drink|calorie_dense"],\n'
        '      "parser_confidence": 0.0\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Rules:\n- Return at most {max_items} items.\n"
        "- Keep item names concise and menu-like.\n"
        "- Remove prices and headers.\n"
        "- No prose, no markdown fences.\n"
        "- parser_confidence must be in [0,1].\n\n"
        f"MENU_TEXT:\n{trimmed}\n"
    )


def _invoke_llm_response_text(prompt: str) -> str:
    if not _llm_available():
        raise RuntimeError("llm_unavailable")

    api_key = str(os.getenv("GEMINI_API_KEY", "") or "").strip()
    model_name = _menu_parser_model_name()
    timeout_sec = _menu_parser_timeout_sec()

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.1,
            "response_mime_type": "application/json",
        },
        request_options={"timeout": float(timeout_sec)},
    )
    return str(getattr(response, "text", "") or "").strip()


def _call_llm_menu_parse(
    *,
    raw_text: str,
    ocr_lines: Optional[List[str]],
    max_items: int,
) -> Tuple[List[Dict[str, Any]], str]:
    try:
        prompt = _build_llm_prompt(raw_text, ocr_lines, max_items=max_items)
        raw_response = _invoke_llm_response_text(prompt)
        if not raw_response:
            return [], "empty_llm_response"

        parsed_payload = _extract_json_payload(raw_response)
        if not isinstance(parsed_payload, dict):
            return [], "invalid_llm_json"

        raw_items = parsed_payload.get("parsed_items")
        if not isinstance(raw_items, list):
            return [], "missing_parsed_items"

        out: List[Dict[str, Any]] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            normalized = _sanitize_item(row, fallback_confidence=0.66)
            if normalized:
                out.append(normalized)

        out = _dedupe_items(out, max_items=max_items)
        if not out:
            return [], "llm_empty_items"
        return out, ""
    except Exception as exc:
        return [], str(exc or "llm_parse_failed")[:220]


def parse_menu_items_with_optional_llm(
    *,
    raw_text: str = "",
    ocr_lines: Optional[List[str]] = None,
    deterministic_items: Optional[List[Dict[str, Any]]] = None,
    max_items: int = 24,
) -> Dict[str, Any]:
    fallback_items = deterministic_items if isinstance(deterministic_items, list) else []
    fallback_structured = _fallback_structured_items(fallback_items, max_items=max_items)

    llm_enabled = _env_bool("ENABLE_LLM_MENU_PARSING", default=False)
    llm_attempted = False
    llm_error = ""
    parse_method = "deterministic"
    structured_items = fallback_structured

    if llm_enabled and _should_try_llm(
        raw_text=str(raw_text or ""),
        ocr_lines=ocr_lines,
        deterministic_items=fallback_items,
    ):
        llm_attempted = True
        llm_items, llm_error = _call_llm_menu_parse(
            raw_text=str(raw_text or ""),
            ocr_lines=ocr_lines,
            max_items=max_items,
        )
        if llm_items:
            parse_method = "llm"
            # Keep deterministic extras only when LLM returns too few rows.
            if len(llm_items) < 3 and fallback_structured:
                structured_items = _dedupe_items(llm_items + fallback_structured, max_items=max_items)
            else:
                structured_items = llm_items
            llm_error = ""

    scoring_items = _to_scoring_items(structured_items, max_items=max_items)
    avg_conf = (
        sum(_safe_float(x.get("parser_confidence"), 0.62) for x in structured_items) / max(1, len(structured_items))
        if structured_items
        else 0.0
    )

    return {
        "parsed_items": scoring_items,
        "structured_items": structured_items,
        "parse_method": parse_method,
        "parse_version": LLM_MENU_PARSE_VERSION,
        "parser_confidence": round(_clamp(avg_conf, 0.0, 1.0), 2),
        "llm_enabled": llm_enabled,
        "llm_attempted": llm_attempted,
        "llm_error": llm_error,
    }


def _place_cuisine_hint(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    primary = str(payload.get("primary_type") or payload.get("primaryType") or "").strip()
    if primary:
        return primary.replace("_", " ")

    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    cleaned: List[str] = []
    for token in types:
        text = _normalized_text(token).replace("_", " ")
        if text and text not in {"restaurant", "food", "point of interest", "establishment", "meal takeaway"}:
            cleaned.append(text)
    return ", ".join(cleaned[:4])


def _build_place_menu_understanding_prompt(
    *,
    place: Dict[str, Any],
    heuristic_items: List[Dict[str, Any]],
    max_items: int,
) -> str:
    payload = place if isinstance(place, dict) else {}
    place_name = str(payload.get("name") or "").strip()
    place_address = str(payload.get("vicinity") or payload.get("address") or "").strip()
    cuisine_hint = _place_cuisine_hint(payload)
    heuristic_names = [
        str((item if isinstance(item, dict) else {}).get("item_name") or "").strip()
        for item in heuristic_items[:6]
    ]
    heuristic_names = [name for name in heuristic_names if name]

    return (
        "You infer likely lighter menu choices for a restaurant when no reliable menu is available.\n"
        "Return ONLY valid JSON with shape:\n"
        "{\n"
        '  "parsed_items": [\n'
        "    {\n"
        '      "item_name": "string",\n'
        '      "category": "bowl|salad|burger|wrap|pizza|sushi|curry|sandwich|taco|burrito|combo|drink|dessert|rice|noodle|plate|other",\n'
        '      "likely_protein": "string",\n'
        '      "likely_carbs": ["string"],\n'
        '      "likely_fats": ["string"],\n'
        '      "health_signals": ["high_protein|lean_protein|high_fiber|fried|deep_fried|creamy_sauce|sugary_drink|calorie_dense"],\n'
        '      "parser_confidence": 0.0\n'
        "    }\n"
        "  ]\n"
        "}\n"
        f"Rules:\n- Return at most {max_items} items.\n"
        "- If confidence is low, use honest category guidance instead of fake exact dishes.\n"
        "- Do not invent western dishes for Indian/temple/canteen contexts.\n"
        "- Prefer cuisine-appropriate lighter options.\n"
        "- parser_confidence must be in [0,1].\n"
        "- No markdown fences, no prose.\n\n"
        f"place_name: {place_name or 'Unknown place'}\n"
        f"place_address: {place_address or 'N/A'}\n"
        f"cuisine_hint: {cuisine_hint or 'N/A'}\n"
        f"heuristic_candidates: {', '.join(heuristic_names) if heuristic_names else 'none'}\n"
    )


def _call_llm_place_menu_understanding(
    *,
    place: Dict[str, Any],
    heuristic_items: List[Dict[str, Any]],
    max_items: int,
) -> Tuple[List[Dict[str, Any]], str]:
    try:
        prompt = _build_place_menu_understanding_prompt(
            place=place,
            heuristic_items=heuristic_items,
            max_items=max_items,
        )
        raw_response = _invoke_llm_response_text(prompt)
        if not raw_response:
            return [], "empty_llm_response"

        parsed_payload = _extract_json_payload(raw_response)
        if not isinstance(parsed_payload, dict):
            return [], "invalid_llm_json"

        raw_items = parsed_payload.get("parsed_items")
        if not isinstance(raw_items, list):
            return [], "missing_parsed_items"

        out: List[Dict[str, Any]] = []
        for row in raw_items:
            if not isinstance(row, dict):
                continue
            normalized = _sanitize_item(row, fallback_confidence=0.58)
            if normalized:
                out.append(normalized)

        out = _dedupe_items(out, max_items=max_items)
        if not out:
            return [], "llm_empty_items"
        return out, ""
    except Exception as exc:
        return [], str(exc or "llm_place_understanding_failed")[:220]


def infer_place_menu_items_with_optional_llm(
    *,
    place: Dict[str, Any],
    heuristic_items: List[Dict[str, Any]] | None = None,
    max_items: int = 3,
) -> Dict[str, Any]:
    fallback_candidates = heuristic_items if isinstance(heuristic_items, list) else []
    fallback_scoring_items: List[Dict[str, Any]] = []
    for row in fallback_candidates[: max(1, max_items)]:
        payload = row if isinstance(row, dict) else {}
        item_name = str(payload.get("item_name") or payload.get("name") or "").strip()
        if not item_name:
            continue
        fallback_scoring_items.append(
            {
                "item_name": item_name,
                "confidence": round(_clamp(_safe_float(payload.get("confidence"), 0.48), 0.3, 0.8), 2),
                "menu_item_source": "heuristic",
            }
        )

    llm_enabled = _env_bool("ENABLE_LLM_MENU_PARSING", default=False)
    llm_attempted = False
    llm_error = ""
    parse_method = "heuristic"
    scoring_items = fallback_scoring_items

    if llm_enabled and _llm_available():
        llm_attempted = True
        llm_items, llm_error = _call_llm_place_menu_understanding(
            place=place if isinstance(place, dict) else {},
            heuristic_items=fallback_candidates,
            max_items=max_items,
        )
        if llm_items:
            parse_method = "llm_inferred"
            scoring_items = [
                {
                    "item_name": str(item.get("item_name") or "").strip(),
                    "confidence": round(_clamp(_safe_float(item.get("parser_confidence"), 0.6), 0.3, 0.92), 2),
                    "menu_item_source": "llm_inferred",
                }
                for item in llm_items
                if str(item.get("item_name") or "").strip()
            ]
            if len(scoring_items) < max_items and fallback_scoring_items:
                existing = {" ".join(str(x.get("item_name") or "").strip().lower().split()) for x in scoring_items}
                for fallback in fallback_scoring_items:
                    key = " ".join(str(fallback.get("item_name") or "").strip().lower().split())
                    if not key or key in existing:
                        continue
                    scoring_items.append(fallback)
                    existing.add(key)
                    if len(scoring_items) >= max_items:
                        break
            llm_error = ""
    elif llm_enabled:
        llm_attempted = True
        llm_error = "llm_unavailable"

    scoring_items = scoring_items[: max(1, max_items)]
    avg_conf = (
        sum(_safe_float(item.get("confidence"), 0.0) for item in scoring_items) / max(1, len(scoring_items))
        if scoring_items
        else 0.0
    )

    return {
        "parsed_items": scoring_items,
        "parse_method": parse_method,
        "parse_version": LLM_MENU_PARSE_VERSION,
        "parser_confidence": round(_clamp(avg_conf, 0.0, 1.0), 2),
        "llm_enabled": llm_enabled,
        "llm_attempted": llm_attempted,
        "llm_error": llm_error,
    }
