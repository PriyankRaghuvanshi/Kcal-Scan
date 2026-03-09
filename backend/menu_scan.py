from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from coach_messages import build_place_coach_message
from llm_menu_parser import parse_menu_items_with_optional_llm
from llm_menu_reasoning import (
    CONF_EXACT_ITEM,
    CONF_SOFT_ITEM,
    CONF_REASONING_FULL,
    CONF_REASONING_USE,
    reason_over_menu,
    candidate_item_name,
    candidate_calories,
    candidate_protein,
)
from menu_item_scoring import score_menu_item
from nutrition_mode import NutritionMode
from personalization_profiles import normalize_personalization_goal, personalization_goal_value
from place_today_decision import evaluate_place_for_today
from restaurant_reality_check import build_restaurant_reality_check


MENU_SCAN_VERSION = "v1"

_MENU_SECTION_TOKENS = {
    "menu",
    "starters",
    "entrees",
    "mains",
    "main",
    "desserts",
    "drinks",
    "beverages",
    "sides",
    "combos",
    "specials",
    "today",
    "chef",
}

_DISH_HINT_TOKENS = (
    "chicken",
    "beef",
    "fish",
    "salmon",
    "tuna",
    "shrimp",
    "prawn",
    "bowl",
    "salad",
    "burger",
    "wrap",
    "sandwich",
    "pizza",
    "taco",
    "burrito",
    "nachos",
    "curry",
    "rice",
    "noodles",
    "steak",
    "sashimi",
    "sushi",
    "paneer",
    "tofu",
    "dal",
    "kebab",
)

_HEAVY_TOKENS = (
    "loaded",
    "double",
    "large",
    "family",
    "fries",
    "fried",
    "crispy",
    "extra cheese",
    "nachos",
    "combo",
    "shake",
    "soda",
    "cream",
    "butter",
)

_PRICE_RE = re.compile(r"[\s\-:]*([$€£₹]\s*)?\d{1,4}(?:[.,]\d{1,2})?\s*$")
_NON_ALPHA_RE = re.compile(r"[^a-zA-Z]+")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _normalized_token(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _strip_noise(line: str) -> str:
    text = str(line or "").replace("\t", " ").strip()
    text = re.sub(r"^[\-\*\u2022•\.\s]+", "", text)
    text = _PRICE_RE.sub("", text).strip()
    text = re.sub(r"\s{2,}", " ", text).strip(" -:")
    return text


def _is_heading_or_noise(line: str) -> bool:
    text = _normalized_token(line)
    if not text:
        return True
    if len(text) < 3:
        return True
    words = text.split()
    if len(words) <= 2 and all(w in _MENU_SECTION_TOKENS for w in words):
        return True
    if text in _MENU_SECTION_TOKENS:
        return True
    letters = _NON_ALPHA_RE.sub("", text)
    if not letters:
        return True
    digit_count = sum(ch.isdigit() for ch in text)
    if digit_count > len(text) * 0.4:
        return True
    if len(words) == 1 and words[0] not in _DISH_HINT_TOKENS:
        return True
    return False


def _line_confidence(line: str) -> float:
    text = _normalized_token(line)
    words = text.split()
    conf = 0.56
    if 2 <= len(words) <= 6:
        conf += 0.14
    if any(token in text for token in _DISH_HINT_TOKENS):
        conf += 0.14
    if any(ch.isdigit() for ch in text):
        conf -= 0.10
    if len(text) > 58:
        conf -= 0.06
    return round(_clamp(conf, 0.35, 0.94), 2)


def parse_menu_items_from_text(
    raw_text: str = "",
    *,
    ocr_lines: Optional[List[str]] = None,
    max_items: int = 24,
) -> List[Dict[str, Any]]:
    source_lines: List[str] = []
    if isinstance(ocr_lines, list) and ocr_lines:
        source_lines = [str(x or "") for x in ocr_lines]
    else:
        source_lines = str(raw_text or "").splitlines()

    out: List[Dict[str, Any]] = []
    seen = set()
    for row in source_lines:
        cleaned = _strip_noise(row)
        if _is_heading_or_noise(cleaned):
            continue
        key = _normalized_token(cleaned)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "item_name": cleaned,
                "confidence": _line_confidence(cleaned),
            }
        )
        if len(out) >= max_items:
            break
    return out


def _resolve_mode(goal: str, cut_mode: bool) -> NutritionMode:
    goal_token = _normalized_token(goal)
    if cut_mode or goal_token in {"fat_loss", "cut", "weight_loss"}:
        return NutritionMode.CUT
    return NutritionMode.DEFAULT


def _place_context(
    *,
    restaurant_name: str,
    place_id: str,
    cuisine: str,
    parsed_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    name = str(restaurant_name or "").strip() or "Restaurant menu"
    cuisine_txt = str(cuisine or "").strip()
    types = [cuisine_txt.lower().replace(" ", "_")] if cuisine_txt else []
    return {
        "name": name,
        "place_id": str(place_id or "").strip(),
        "primary_type": cuisine_txt.lower().replace(" ", "_") if cuisine_txt else "",
        "types": types,
        "menu_items": [{"item_name": str(x.get("item_name") or ""), "confidence": float(_safe_float(x.get("confidence"), 0.6))} for x in parsed_items],
    }


def _sort_scored_items(scored: List[Dict[str, Any]], mode: NutritionMode) -> List[Dict[str, Any]]:
    if mode == NutritionMode.CUT:
        return sorted(
            scored,
            key=lambda row: (
                int(_safe_float(row.get("item_score"), 0.0)),
                int(_safe_float((row.get("item_score_breakdown") or {}).get("calorie_control"), 0.0)),
                int(_safe_float((row.get("item_score_breakdown") or {}).get("protein_density"), 0.0)),
            ),
            reverse=True,
        )
    return sorted(scored, key=lambda row: int(_safe_float(row.get("item_score"), 0.0)), reverse=True)


def _score_menu_items(
    *,
    place: Dict[str, Any],
    parsed_items: List[Dict[str, Any]],
    mode: NutritionMode,
    goal: str,
) -> List[Dict[str, Any]]:
    place_text = " ".join(
        [
            _normalized_token(place.get("name")),
            _normalized_token(place.get("primary_type")),
            _normalized_token(" ".join(place.get("types") or [])),
        ]
    ).strip()
    scored: List[Dict[str, Any]] = []
    for item in parsed_items:
        out = score_menu_item(
            {
                "item_name": str(item.get("item_name") or "").strip(),
                "confidence": _safe_float(item.get("confidence"), 0.6),
            },
            context={
                "place": place,
                "place_text": place_text,
                "menu_source": "menu_scan_ocr",
                "mode": mode.value,
                "personalization_goal": goal,
            },
            mode=mode,
            personalization_goal=goal,
        )
        scored.append(out)
    return _sort_scored_items(scored, mode=mode)


def _to_fit_bool(decision_token: Any) -> Optional[bool]:
    token = str(decision_token or "").strip().upper()
    if token == "YES":
        return True
    if token == "NO":
        return False
    return None


def _attach_fit(
    item: Dict[str, Any],
    *,
    remaining_calories: Optional[float],
    remaining_protein_g: Optional[float],
) -> Dict[str, Any]:
    row = dict(item)
    fit = evaluate_place_for_today(
        estimated_calories=row.get("estimated_calories"),
        estimated_protein_g=row.get("estimated_protein_g"),
        remaining_calories=remaining_calories,
        remaining_protein_g=remaining_protein_g,
        health_score=min(10.0, max(1.0, _safe_float(row.get("item_score"), 60.0) / 10.0)),
    )
    row["fit_for_today"] = _to_fit_bool(fit.get("decision_today"))
    row["decision_today"] = fit.get("decision_today")
    row["decision_reason"] = str(fit.get("decision_reason") or "")
    row["fits_remaining_calories"] = fit.get("fits_remaining_calories")
    row["fits_remaining_protein"] = fit.get("fits_remaining_protein")
    row["decision_confidence"] = fit.get("decision_confidence")
    return row


def _avoid_rank(item: Dict[str, Any]) -> float:
    text = _normalized_token(item.get("item_name"))
    calories = _safe_float(item.get("estimated_calories"), 520.0)
    protein = _safe_float(item.get("estimated_protein_g"), 30.0)
    score = _safe_float(item.get("item_score"), 60.0)
    penalty = 0.0
    penalty += max(0.0, calories - 700.0) / 110.0
    penalty += max(0.0, 24.0 - protein) / 5.0
    penalty += max(0.0, 70.0 - score) / 10.0
    if any(token in text for token in _HEAVY_TOKENS):
        penalty += 3.5
    return penalty


def _avoid_reason(item: Dict[str, Any]) -> str:
    calories = int(_safe_float(item.get("estimated_calories"), 0.0))
    if calories >= 950:
        return "Very calorie-dense and difficult to fit on a cut."
    if calories >= 760:
        return "Harder to fit today unless portions stay very small."
    return "Usually harder to fit when calories are tight."


def _scan_confidence(
    *,
    parsed_items: List[Dict[str, Any]],
    top_recommendations: List[Dict[str, Any]],
    ocr_confidence: float,
) -> float:
    if not parsed_items:
        return round(_clamp(max(0.2, ocr_confidence * 0.7), 0.2, 0.46), 2)
    avg_parse = sum(_safe_float(x.get("confidence"), 0.5) for x in parsed_items) / max(1, len(parsed_items))
    avg_top = (
        sum(_safe_float(x.get("confidence"), 0.5) for x in top_recommendations) / max(1, len(top_recommendations))
        if top_recommendations
        else 0.5
    )
    density = min(1.0, len(parsed_items) / 10.0)
    val = (avg_parse * 0.36) + (avg_top * 0.26) + (ocr_confidence * 0.22) + (density * 0.16)
    return round(_clamp(val, 0.25, 0.95), 2)


def _mobile_why(item: Dict[str, Any], rank: int) -> str:
    protein = int(_safe_float(item.get("estimated_protein_g"), 0.0) or 0)
    calories = int(_safe_float(item.get("estimated_calories"), 0.0) or 0)
    text = str(item.get("short_reason") or "").strip()

    if rank == 1 and protein >= 35 and calories <= 620:
        return "Best protein-to-calorie choice on this menu."
    if protein >= 35:
        return "High protein with manageable calories."
    if calories <= 560:
        return "Lighter calories and easier to fit today."
    if text:
        return text[:96]
    return "Balanced lighter option for this menu."


def _top_choices_payload(top_recommendations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for idx, row in enumerate(top_recommendations[:3], start=1):
        if not isinstance(row, dict):
            continue
        item_name = str(row.get("item_name") or "").strip()
        if not item_name:
            continue
        out.append(
            {
                "item_name": item_name,
                "estimated_calories": int(_safe_float(row.get("estimated_calories"), 0.0) or 0),
                "estimated_protein_g": int(_safe_float(row.get("estimated_protein_g"), 0.0) or 0),
                "why": _mobile_why(row, idx),
            }
        )
    return out


def _best_high_protein_choice(top_recommendations: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    candidates = [row for row in (top_recommendations or []) if isinstance(row, dict) and str(row.get("item_name") or "").strip()]
    if not candidates:
        return None
    candidates.sort(
        key=lambda row: (
            int(_safe_float(row.get("estimated_protein_g"), 0.0) or 0),
            -int(_safe_float(row.get("estimated_calories"), 9999.0) or 9999),
            int(_safe_float(row.get("item_score"), 0.0) or 0),
        ),
        reverse=True,
    )
    best = candidates[0]
    return {
        "item_name": str(best.get("item_name") or "").strip(),
        "estimated_calories": int(_safe_float(best.get("estimated_calories"), 0.0) or 0),
        "estimated_protein_g": int(_safe_float(best.get("estimated_protein_g"), 0.0) or 0),
        "why": "Highest protein option with practical calories.",
    }


def _smart_swaps(
    *,
    top_recommendations: List[Dict[str, Any]],
    better_swap: Optional[Dict[str, Any]],
    avoid_if_cutting: Optional[Dict[str, Any]],
) -> List[str]:
    out: List[str] = []

    avoid_name = str((avoid_if_cutting or {}).get("item_name") or "").strip()
    if better_swap and isinstance(better_swap, dict):
        swap_name = str(better_swap.get("item_name") or "").strip()
        if swap_name and avoid_name:
            out.append(f"Choose {swap_name} instead of {avoid_name}")
        elif swap_name:
            out.append(f"Choose {swap_name} as a lighter swap")
        else:
            swap_reason = str(better_swap.get("short_reason") or "").strip()
            if swap_reason:
                out.append(swap_reason)

    for row in top_recommendations[:3]:
        if not isinstance(row, dict):
            continue
        swap_hint = str(row.get("swap_suggestion") or "").strip()
        if swap_hint:
            out.append(swap_hint)

    deduped: List[str] = []
    seen = set()
    for row in out:
        key = _normalized_token(row)
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row[:110])
        if len(deduped) >= 3:
            break
    return deduped


def build_menu_scan_response(
    *,
    raw_menu_text: str = "",
    ocr_lines: Optional[List[str]] = None,
    ocr_confidence: float = 0.0,
    restaurant_name: str = "",
    place_id: str = "",
    cuisine: str = "",
    remaining_calories: Optional[float] = None,
    remaining_protein_g: Optional[float] = None,
    goal: str = "",
    cut_mode: bool = False,
) -> Dict[str, Any]:
    deterministic_parsed = parse_menu_items_from_text(raw_menu_text, ocr_lines=ocr_lines)
    parse_bundle = parse_menu_items_with_optional_llm(
        raw_text=raw_menu_text,
        ocr_lines=ocr_lines,
        deterministic_items=deterministic_parsed,
        max_items=24,
    )
    parsed = (
        parse_bundle.get("parsed_items")
        if isinstance(parse_bundle.get("parsed_items"), list)
        else deterministic_parsed
    )
    structured_parsed = (
        parse_bundle.get("structured_items")
        if isinstance(parse_bundle.get("structured_items"), list)
        else []
    )
    parse_method = str(parse_bundle.get("parse_method") or "deterministic").strip() or "deterministic"
    parse_version = str(parse_bundle.get("parse_version") or MENU_SCAN_VERSION).strip() or MENU_SCAN_VERSION
    parser_confidence = round(_safe_float(parse_bundle.get("parser_confidence"), 0.0), 2)
    llm_attempted = bool(parse_bundle.get("llm_attempted"))
    llm_error = str(parse_bundle.get("llm_error") or "").strip()

    goal_token = _normalized_token(goal)
    mode = _resolve_mode(goal_token, bool(cut_mode))
    goal_value = personalization_goal_value(normalize_personalization_goal(goal_token))

    if len(parsed) < 2:
        fallback_response = {
            "title": "Menu scan needs a clearer photo",
            "subtitle": "We couldn't confidently read enough menu items yet.",
            "parsed_menu_items": parsed[:8],
            "parsed_menu_items_structured": structured_parsed[:8],
            "top_recommendations": [],
            "top_choices": [],
            "best_high_protein_choice": None,
            "better_swap": None,
            "avoid_if_cutting": None,
            "avoid_if_cutting_items": [],
            "smart_swaps": [],
            "coach_message": {
                "headline": "Try a straighter photo with better lighting.",
                "supporting_text": "Include item names clearly and avoid glare.",
            },
            "parse_method": parse_method,
            "parse_version": parse_version,
            "parser_confidence": parser_confidence,
            "llm_parser_used": bool(parse_method == "llm"),
            "llm_parser_attempted": llm_attempted,
            "scan_confidence": _scan_confidence(parsed_items=parsed, top_recommendations=[], ocr_confidence=_safe_float(ocr_confidence, 0.0)),
            "scan_version": MENU_SCAN_VERSION,
        }
        if llm_attempted and llm_error and parse_method != "llm":
            fallback_response["parse_fallback_reason"] = llm_error[:120]
        return fallback_response

    place = _place_context(
        restaurant_name=restaurant_name,
        place_id=place_id,
        cuisine=cuisine,
        parsed_items=parsed,
    )
    scored_items = _score_menu_items(place=place, parsed_items=parsed, mode=mode, goal=goal_token)
    top_items = scored_items[:3]
    enriched_top = [
        _attach_fit(
            row,
            remaining_calories=remaining_calories,
            remaining_protein_g=remaining_protein_g,
        )
        for row in top_items
    ]

    if not enriched_top:
        fallback_response = {
            "title": "Menu scan needs a clearer photo",
            "subtitle": "We couldn't score enough clear menu items from this photo.",
            "parsed_menu_items": parsed[:8],
            "parsed_menu_items_structured": structured_parsed[:8],
            "top_recommendations": [],
            "top_choices": [],
            "best_high_protein_choice": None,
            "better_swap": None,
            "avoid_if_cutting": None,
            "avoid_if_cutting_items": [],
            "smart_swaps": [],
            "coach_message": {
                "headline": "Try another scan in brighter light.",
                "supporting_text": "A clearer image helps us rank menu items accurately.",
            },
            "parse_method": parse_method,
            "parse_version": parse_version,
            "parser_confidence": parser_confidence,
            "llm_parser_used": bool(parse_method == "llm"),
            "llm_parser_attempted": llm_attempted,
            "scan_confidence": _scan_confidence(parsed_items=parsed, top_recommendations=[], ocr_confidence=_safe_float(ocr_confidence, 0.0)),
            "scan_version": MENU_SCAN_VERSION,
        }
        if llm_attempted and llm_error and parse_method != "llm":
            fallback_response["parse_fallback_reason"] = llm_error[:120]
        return fallback_response

    best = enriched_top[0]
    better = enriched_top[1] if len(enriched_top) > 1 else None

    # Run LLM reasoning over the real OCR text to get structured candidates.
    # This is the highest-value call in the scan flow — the model sees the actual
    # menu and returns specific item names, not cuisine stereotypes.
    llm_reasoning: Dict[str, Any] = {}
    try:
        llm_reasoning = reason_over_menu(
            menu_text=raw_menu_text,
            place_name=str(place.get("name") or restaurant_name or "").strip(),
            goal=goal_token,
            cut_mode=bool(mode == NutritionMode.CUT),
            remaining_calories=remaining_calories,
            remaining_protein_g=remaining_protein_g,
        )
    except Exception:
        llm_reasoning = {}

    llm_used = bool(llm_reasoning.get("llm_reasoning_used"))
    llm_conf = float(_safe_float(llm_reasoning.get("reasoning_confidence"), 0.0))

    # Override scored best_choice_here with LLM candidate when confidence is high
    # enough and the LLM picked a more specific menu item name.
    llm_best_candidate = llm_reasoning.get("best_choice_here") if isinstance(llm_reasoning.get("best_choice_here"), dict) else {}
    # Apply centralized confidence policy:
    #   CONF_EXACT_ITEM (0.65) — per-candidate minimum for exact item name
    #   CONF_REASONING_FULL (0.65) — overall minimum to fully promote best_choice
    llm_best_name = candidate_item_name(llm_best_candidate, min_confidence=CONF_EXACT_ITEM) if llm_best_candidate else ""
    if llm_used and llm_best_name and llm_conf >= CONF_REASONING_FULL:
        best_choice_item_name = llm_best_name
        best_choice_calories = candidate_calories(llm_best_candidate) or int(_safe_float(best.get("estimated_calories"), 0.0) or 0)
        best_choice_protein = candidate_protein(llm_best_candidate) or int(_safe_float(best.get("estimated_protein_g"), 0.0) or 0)
        best_choice_why = str(llm_best_candidate.get("why") or best.get("short_reason") or "")
    else:
        best_choice_item_name = str(best.get("item_name") or "")
        best_choice_calories = int(_safe_float(best.get("estimated_calories"), 0.0) or 0)
        best_choice_protein = int(_safe_float(best.get("estimated_protein_g"), 0.0) or 0)
        best_choice_why = str(best.get("short_reason") or "")

    # Build better_swap from LLM candidate when available and distinct.
    # Uses CONF_EXACT_ITEM for per-candidate name, CONF_REASONING_USE for overall gate.
    llm_swap_candidate = llm_reasoning.get("better_swap") if isinstance(llm_reasoning.get("better_swap"), dict) else {}
    llm_swap_name = candidate_item_name(llm_swap_candidate, min_confidence=CONF_EXACT_ITEM) if llm_swap_candidate else ""
    if llm_used and llm_swap_name and llm_conf >= CONF_REASONING_USE and llm_swap_name != best_choice_item_name:
        better_swap_item = {
            "item_name": llm_swap_name,
            "estimated_calories": candidate_calories(llm_swap_candidate) or (int(_safe_float(better.get("estimated_calories"), 0.0) or 0) if better else 0),
            "estimated_protein_g": candidate_protein(llm_swap_candidate) or (int(_safe_float(better.get("estimated_protein_g"), 0.0) or 0) if better else 0),
            "short_reason": str(llm_swap_candidate.get("why") or (better.get("short_reason") if better else "") or "A lighter alternative from this menu."),
            "swap_tip": str(llm_swap_candidate.get("swap_tip") or ""),
        }
    else:
        better_swap_item = (
            {
                "item_name": str(better.get("item_name") or ""),
                "estimated_calories": int(_safe_float(better.get("estimated_calories"), 0.0) or 0),
                "estimated_protein_g": int(_safe_float(better.get("estimated_protein_g"), 0.0) or 0),
                "short_reason": str(better.get("short_reason") or "A solid lighter swap if calories are tight."),
            }
            if isinstance(better, dict)
            else None
        )

    # Build avoid_if_cutting from LLM candidate when available.
    # Uses CONF_EXACT_ITEM for name, CONF_REASONING_USE for overall gate.
    llm_avoid_candidate = llm_reasoning.get("avoid_if_cutting") if isinstance(llm_reasoning.get("avoid_if_cutting"), dict) else {}
    llm_avoid_name = candidate_item_name(llm_avoid_candidate, min_confidence=CONF_EXACT_ITEM) if llm_avoid_candidate else ""
    avoid_src = max(scored_items, key=_avoid_rank) if scored_items else None
    if llm_used and llm_avoid_name and llm_conf >= CONF_REASONING_USE:
        avoid = {
            "item_name": llm_avoid_name,
            "estimated_calories": candidate_calories(llm_avoid_candidate) or (int(_safe_float(avoid_src.get("estimated_calories"), 0.0) or 0) if avoid_src else 0),
            "short_reason": str(llm_avoid_candidate.get("why") or "Highest calorie density on this menu."),
        }
    else:
        avoid = (
            {
                "item_name": str(avoid_src.get("item_name") or ""),
                "estimated_calories": int(_safe_float(avoid_src.get("estimated_calories"), 0.0) or 0),
                "short_reason": _avoid_reason(avoid_src),
            }
            if isinstance(avoid_src, dict)
            else None
        )

    top_choices = _top_choices_payload(enriched_top)
    best_high_protein = _best_high_protein_choice(enriched_top)
    smart_swaps = _smart_swaps(
        top_recommendations=enriched_top,
        better_swap=better_swap_item,
        avoid_if_cutting=avoid,
    )

    reality_place = dict(place)
    reality_place["menu_items"] = [
        {
            "item_name": str(x.get("item_name") or ""),
            "estimated_calories": int(_safe_float(x.get("estimated_calories"), 0.0) or 0),
            "estimated_protein_g": int(_safe_float(x.get("estimated_protein_g"), 0.0) or 0),
        }
        for x in scored_items[:8]
    ]
    recommended_order = {
        "item_name": best_choice_item_name or str(best.get("item_name") or ""),
        "estimated_calories": best_choice_calories or int(_safe_float(best.get("estimated_calories"), 520.0) or 520),
        "estimated_protein_g": best_choice_protein or int(_safe_float(best.get("estimated_protein_g"), 30.0) or 30),
    }
    reality_check = build_restaurant_reality_check(
        reality_place,
        recommended_order=recommended_order,
        context={
            "top_menu_item": best,
            "llm_reasoning_candidates": llm_reasoning,
        },
    )

    today_fit = {
        "decision": best.get("decision_today"),
        "decision_reason": best.get("decision_reason"),
    }
    coach_message = build_place_coach_message(
        {
            "name": place.get("name"),
            "fit_for_today": best.get("fit_for_today"),
            "decision_today": best.get("decision_today"),
            "decision_reason": best.get("decision_reason"),
            "health_score_100": int(_safe_float(best.get("item_score"), 0.0) or 0),
            "personalization_goal": goal_value,
            "cut_mode_active": bool(mode == NutritionMode.CUT),
            "remaining_protein_g": remaining_protein_g,
        },
        top_menu_item=best,
        today_fit=today_fit,
        reality_check=reality_check,
        context={
            "goal": goal_value,
            "cut_mode": bool(mode == NutritionMode.CUT),
            "remaining_protein_g": remaining_protein_g,
        },
    )

    response = {
        "title": "Best Choice Here",
        "subtitle": "AI analyzed this restaurant menu",
        "best_choice_here": {
            "item_name": best_choice_item_name or str(best.get("item_name") or ""),
            "item_score": int(_safe_float(best.get("item_score"), 0.0) or 0),
            "estimated_calories": best_choice_calories or int(_safe_float(best.get("estimated_calories"), 0.0) or 0),
            "estimated_protein_g": best_choice_protein or int(_safe_float(best.get("estimated_protein_g"), 0.0) or 0),
            "fit_for_today": best.get("fit_for_today"),
            "short_reason": best_choice_why or str(best.get("short_reason") or ""),
            "recommendation_tags": list(best.get("recommendation_tags") or []),
            "llm_reasoning_used": llm_used,
        },
        "menu_summary": str(llm_reasoning.get("menu_summary") or "") if llm_used else "",
        "parsed_menu_items": parsed[:18],
        "parsed_menu_items_structured": structured_parsed[:18],
        "top_recommendations": enriched_top,
        "top_choices": top_choices,
        "best_high_protein_choice": best_high_protein,
        "better_swap": better_swap_item,
        "avoid_if_cutting": avoid,
        "avoid_if_cutting_items": [str(avoid.get("item_name") or "").strip()] if isinstance(avoid, dict) and str(avoid.get("item_name") or "").strip() else [],
        "smart_swaps": smart_swaps,
        "coach_message": coach_message,
        "reality_check": reality_check,
        "parse_method": parse_method,
        "parse_version": parse_version,
        "parser_confidence": parser_confidence,
        "llm_parser_used": bool(parse_method == "llm"),
        "llm_parser_attempted": llm_attempted,
        "llm_reasoning_used": llm_used,
        "llm_reasoning_confidence": round(llm_conf, 2),
        "scan_confidence": _scan_confidence(
            parsed_items=parsed,
            top_recommendations=enriched_top,
            ocr_confidence=_safe_float(ocr_confidence, 0.0),
        ),
        "scan_version": MENU_SCAN_VERSION,
    }
    if llm_attempted and llm_error and parse_method != "llm":
        response["parse_fallback_reason"] = llm_error[:120]
    return response
