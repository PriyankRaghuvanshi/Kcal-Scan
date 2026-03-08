from __future__ import annotations

from typing import Any, Dict, List, Tuple

from llm_explanation_copy import maybe_rewrite_explanation_copy
from restaurant_macro_estimator import estimate_restaurant_macros


RESTAURANT_REALITY_CHECK_VERSION = "v1"
REALITY_CHECK_SHARE_CARD_VERSION = "v1"


# Centralized rule map for typical-vs-smarter order comparisons.
# v1 is deterministic and easy to tune.
TYPICAL_ORDER_RULES: List[Dict[str, Any]] = [
    {
        "rule_id": "fried_chicken",
        "tokens": ("fried chicken", "crispy", "bucket", "wings"),
        "typical_name": "Fried chicken combo meal",
        "typical_calories": 1020,
        "typical_protein_g": 32,
        "smarter_name": "Grilled chicken + side salad",
        "smarter_calories": 590,
        "smarter_protein_g": 42,
    },
    {
        "rule_id": "burger_fast_food",
        "tokens": ("burger", "fast_food", "fast food", "drive", "mcd", "combo"),
        "typical_name": "Burger + fries + soda",
        "typical_calories": 1080,
        "typical_protein_g": 28,
        "smarter_name": "Grilled wrap + water",
        "smarter_calories": 560,
        "smarter_protein_g": 38,
    },
    {
        "rule_id": "pizza",
        "tokens": ("pizza", "pizzeria", "slice"),
        "typical_name": "Large pizza combo",
        "typical_calories": 980,
        "typical_protein_g": 30,
        "smarter_name": "Thin crust + protein topping",
        "smarter_calories": 620,
        "smarter_protein_g": 34,
    },
    {
        "rule_id": "mexican",
        "tokens": ("mexican", "burrito", "taco", "quesadilla"),
        "typical_name": "Loaded burrito combo",
        "typical_calories": 940,
        "typical_protein_g": 29,
        "smarter_name": "Chicken burrito bowl",
        "smarter_calories": 590,
        "smarter_protein_g": 41,
    },
    {
        "rule_id": "cafe",
        "tokens": ("cafe", "coffee", "brunch", "bakery"),
        "typical_name": "Pastry + flavored drink",
        "typical_calories": 760,
        "typical_protein_g": 14,
        "smarter_name": "Egg + chicken plate",
        "smarter_calories": 470,
        "smarter_protein_g": 33,
    },
    {
        "rule_id": "sushi_japanese",
        "tokens": ("sushi", "japanese", "tempura", "teriyaki"),
        "typical_name": "Tempura roll combo",
        "typical_calories": 860,
        "typical_protein_g": 26,
        "smarter_name": "Sashimi + rice-controlled bowl",
        "smarter_calories": 540,
        "smarter_protein_g": 39,
    },
    {
        "rule_id": "indian",
        "tokens": ("indian", "curry", "naan", "biryani"),
        "typical_name": "Creamy curry + rice + naan",
        "typical_calories": 980,
        "typical_protein_g": 30,
        "smarter_name": "Tandoori + dal + roti",
        "smarter_calories": 620,
        "smarter_protein_g": 40,
    },
    {
        "rule_id": "thai_chinese",
        "tokens": ("thai", "chinese", "wok", "noodle", "stir fry"),
        "typical_name": "Saucy fried noodle combo",
        "typical_calories": 910,
        "typical_protein_g": 24,
        "smarter_name": "Lean stir-fry + steamed rice",
        "smarter_calories": 600,
        "smarter_protein_g": 35,
    },
    {
        "rule_id": "grill_healthy",
        "tokens": ("grill", "healthy", "bowl", "protein", "salad", "kebab"),
        "typical_name": "Large combo with extra sauces",
        "typical_calories": 900,
        "typical_protein_g": 32,
        "smarter_name": "Quarter chicken + salad",
        "smarter_calories": 540,
        "smarter_protein_g": 44,
    },
    {
        "rule_id": "mediterranean",
        "tokens": ("mediterranean", "shawarma", "falafel", "hummus"),
        "typical_name": "Loaded wrap + fries",
        "typical_calories": 900,
        "typical_protein_g": 27,
        "smarter_name": "Chicken shawarma bowl",
        "smarter_calories": 560,
        "smarter_protein_g": 39,
    },
]


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(value)))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except Exception:
        return int(default)


def _clip(text: Any, max_len: int, fallback: str) -> str:
    value = str(text or "").strip()
    if not value:
        value = fallback
    if len(value) <= max_len:
        return value
    return value[: max(0, max_len - 1)].rstrip() + "..."


def _norm_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _place_text(place: Dict[str, Any]) -> str:
    payload = place if isinstance(place, dict) else {}
    name = str(payload.get("name") or "").strip().lower()
    address = str(payload.get("address") or payload.get("vicinity") or "").strip().lower()
    primary = str(payload.get("primary_type") or payload.get("primaryType") or "").strip().lower()
    types = payload.get("types") if isinstance(payload.get("types"), list) else []
    type_text = " ".join(str(t or "").strip().lower() for t in types)
    return " ".join(x for x in [name, address, primary, type_text] if x)


def _extract_menu_items(place: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload = place if isinstance(place, dict) else {}

    raw_candidates: List[Any] = []
    for key in ("menu_items", "menuItems", "menu", "items"):
        value = payload.get(key)
        if isinstance(value, list) and value:
            raw_candidates.extend(value)
            break

    out: List[Dict[str, Any]] = []
    for row in raw_candidates:
        if isinstance(row, str) and row.strip():
            out.append({"name": row.strip()})
            continue

        if not isinstance(row, dict):
            continue

        name = str(row.get("item_name") or row.get("name") or row.get("title") or "").strip()
        if not name:
            continue

        out.append(
            {
                "name": name,
                "estimated_calories": _safe_int(row.get("estimated_calories", row.get("calories")), 0),
                "estimated_protein_g": _safe_int(row.get("estimated_protein_g", row.get("protein_g")), 0),
                "confidence": float(_safe_float(row.get("confidence", row.get("macro_confidence")), 0.0)),
            }
        )

    return out


def _with_macro_estimate(item_name: str, place: Dict[str, Any], calories: int, protein_g: int) -> Dict[str, Any]:
    estimate = estimate_restaurant_macros(
        item_name=item_name,
        cuisine_hint=_place_text(place),
        place=place,
        input_calories=calories if calories > 0 else None,
        input_protein_g=protein_g if protein_g > 0 else None,
    )

    est_cal = _safe_int(estimate.get("estimated_calories"), calories if calories > 0 else 520)
    est_protein = _safe_int(estimate.get("estimated_protein_g"), protein_g if protein_g > 0 else 30)

    # Preserve provided macro anchors strongly when available.
    if calories > 0:
        est_cal = _safe_int((0.82 * float(calories)) + (0.18 * float(est_cal)), calories)
    if protein_g > 0:
        est_protein = _safe_int((0.82 * float(protein_g)) + (0.18 * float(est_protein)), protein_g)
    est_conf = float(_safe_float(estimate.get("macro_confidence"), 0.58))

    return {
        "name": _clip(item_name, 72, "Smart order"),
        "estimated_calories": int(max(120, est_cal)),
        "estimated_protein_g": int(max(6, est_protein)),
        "confidence": round(_clamp(est_conf, 0.35, 0.92), 2),
    }


def _combo_keyword_bonus(name: str) -> int:
    text = _norm_text(name)
    if not text:
        return 0

    heavy_tokens = (
        "combo",
        "fries",
        "soda",
        "coke",
        "shake",
        "loaded",
        "bucket",
        "large",
        "double",
        "family",
        "tempura",
        "cream",
        "naan",
    )
    healthy_tokens = (
        "grilled",
        "salad",
        "water",
        "sashimi",
        "light",
        "lean",
        "protein bowl",
        "roti",
    )

    bonus = sum(1 for token in heavy_tokens if token in text)
    penalty = sum(1 for token in healthy_tokens if token in text)
    return int(max(0, bonus - penalty))


def _best_rule(place: Dict[str, Any]) -> Tuple[Dict[str, Any], int]:
    text = _place_text(place)
    selected = None
    hits = 0
    for rule in TYPICAL_ORDER_RULES:
        rule_hits = sum(1 for token in rule.get("tokens", ()) if token in text)
        if rule_hits > hits:
            hits = rule_hits
            selected = rule

    if selected:
        return selected, hits

    return {
        "rule_id": "generic",
        "typical_name": "Combo meal + sugary drink",
        "typical_calories": 860,
        "typical_protein_g": 26,
        "smarter_name": "Lighter menu option + water",
        "smarter_calories": 560,
        "smarter_protein_g": 34,
    }, 0


def _infer_typical_order(place: Dict[str, Any], menu_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    if menu_items:
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for item in menu_items:
            row = _with_macro_estimate(
                item_name=str(item.get("name") or "Typical meal"),
                place=place,
                calories=_safe_int(item.get("estimated_calories"), 0),
                protein_g=_safe_int(item.get("estimated_protein_g"), 0),
            )
            bonus = _combo_keyword_bonus(str(item.get("name") or "")) * 80
            rank = float(row["estimated_calories"]) + float(bonus) - float(row["estimated_protein_g"]) * 1.2
            ranked.append((rank, row))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        typical = ranked[0][1]
        typical["confidence"] = round(_clamp(typical.get("confidence", 0.62) + (0.1 if len(menu_items) >= 3 else 0.05), 0.4, 0.92), 2)
        return typical

    rule, hits = _best_rule(place)
    typical = _with_macro_estimate(
        item_name=str(rule.get("typical_name") or "Combo meal"),
        place=place,
        calories=_safe_int(rule.get("typical_calories"), 860),
        protein_g=_safe_int(rule.get("typical_protein_g"), 26),
    )
    typical["confidence"] = round(_clamp(0.58 + (0.08 if hits >= 2 else 0.04 if hits == 1 else -0.06), 0.35, 0.9), 2)
    return typical


def _infer_smarter_order(
    place: Dict[str, Any],
    menu_items: List[Dict[str, Any]],
    recommended_order: Dict[str, Any],
    context: Dict[str, Any],
) -> Dict[str, Any]:
    rec = recommended_order if isinstance(recommended_order, dict) else {}
    ctx = context if isinstance(context, dict) else {}

    rec_name = str(
        rec.get("item_name")
        or rec.get("best_order")
        or rec.get("name")
        or rec.get("personalized_best_order")
        or rec.get("best_order_for_cut")
        or ""
    ).strip()
    rec_cal = _safe_int(rec.get("estimated_calories"), 0)
    rec_protein = _safe_int(rec.get("estimated_protein_g"), 0)
    rec_conf = float(_safe_float(rec.get("confidence", rec.get("order_confidence")), 0.0))

    if rec_name:
        out = _with_macro_estimate(rec_name, place, rec_cal, rec_protein)
        out["confidence"] = round(_clamp(max(out["confidence"], rec_conf or 0.0), 0.4, 0.93), 2)
        return out

    ctx_top_item = ctx.get("top_menu_item") if isinstance(ctx.get("top_menu_item"), dict) else {}
    top_name = str(
        ctx_top_item.get("item_name")
        or ctx_top_item.get("name")
        or ctx_top_item.get("title")
        or ""
    ).strip()
    if top_name:
        out = _with_macro_estimate(
            top_name,
            place,
            _safe_int(ctx_top_item.get("estimated_calories", ctx_top_item.get("calories")), 0),
            _safe_int(ctx_top_item.get("estimated_protein_g", ctx_top_item.get("protein_g")), 0),
        )
        out["confidence"] = round(
            _clamp(max(out["confidence"], float(_safe_float(ctx_top_item.get("confidence"), 0.68))), 0.4, 0.93),
            2,
        )
        return out

    if menu_items:
        ranked: List[Tuple[float, Dict[str, Any]]] = []
        for item in menu_items:
            row = _with_macro_estimate(
                item_name=str(item.get("name") or "Smart pick"),
                place=place,
                calories=_safe_int(item.get("estimated_calories"), 0),
                protein_g=_safe_int(item.get("estimated_protein_g"), 0),
            )
            protein_density = (float(row["estimated_protein_g"]) / max(1.0, float(row["estimated_calories"]))) * 1000.0
            score = (protein_density * 1.5) + (float(row["estimated_protein_g"]) * 1.1) - (float(row["estimated_calories"]) * 0.08)
            score -= float(_combo_keyword_bonus(str(item.get("name") or ""))) * 35.0
            ranked.append((score, row))

        ranked.sort(key=lambda pair: pair[0], reverse=True)
        smart = ranked[0][1]
        smart["confidence"] = round(_clamp(smart.get("confidence", 0.58) + (0.08 if len(menu_items) >= 2 else 0.04), 0.4, 0.92), 2)
        return smart

    rule, _ = _best_rule(place)
    smart = _with_macro_estimate(
        item_name=str(rule.get("smarter_name") or "Lighter menu option + water"),
        place=place,
        calories=_safe_int(rule.get("smarter_calories"), 560),
        protein_g=_safe_int(rule.get("smarter_protein_g"), 34),
    )
    smart["confidence"] = round(_clamp(smart.get("confidence", 0.56) + 0.02, 0.38, 0.9), 2)
    return smart


def _build_short_reason(calories_saved: int, protein_diff: int) -> str:
    if calories_saved >= 450 and protein_diff >= 0:
        return "You save big calories and keep protein strong."
    if calories_saved >= 300 and protein_diff >= 8:
        return "Much better calorie control with stronger protein."
    if calories_saved >= 220 and protein_diff >= 0:
        return "You save calories without giving up useful protein."
    if calories_saved >= 140 and protein_diff >= 10:
        return "Fewer calories and more protein for your goal."
    if protein_diff >= 10:
        return "Similar calories, but much better protein quality."
    if calories_saved > 0:
        return "Better calorie control with a smarter order choice."
    return "Smarter pick for steadier calories and protein balance."


def build_reality_check_share_card(
    *,
    place_name: Any,
    typical_calories: Any,
    smarter_calories: Any,
    calories_saved: Any,
    smarter_order: Any,
    protein_difference_g: Any,
) -> Dict[str, Any]:
    saved = int(max(0, _safe_int(calories_saved, 0)))
    protein_diff = int(_safe_int(protein_difference_g, 0))

    subtitle = f"I saved {saved} calories just by ordering smarter." if saved > 0 else "Smarter order, easier to stay on track."

    badges: List[str] = ["Smarter Order"]
    if saved >= 250:
        badges.append("Big Calorie Save")
    else:
        badges.append("Better Cut Choice")
    if protein_diff >= 8:
        badges.append("Protein Upgrade")

    deduped: List[str] = []
    seen = set()
    for badge in badges:
        label = _clip(badge, 24, "Smart Choice")
        if label in seen:
            continue
        seen.add(label)
        deduped.append(label)

    return {
        "title": "Restaurant Reality Check",
        "place_name": _clip(place_name, 40, "Nearby Place"),
        "typical_calories": int(max(0, _safe_int(typical_calories, 0))),
        "smarter_calories": int(max(0, _safe_int(smarter_calories, 0))),
        "calories_saved": int(saved),
        "smarter_order": _clip(smarter_order, 64, "Smarter order"),
        "subtitle": _clip(subtitle, 88, "I made a smarter order choice."),
        "badges": deduped[:3],
        "share_card_version": REALITY_CHECK_SHARE_CARD_VERSION,
    }


def build_restaurant_reality_check(
    place: Dict[str, Any],
    recommended_order: Dict[str, Any] | None = None,
    context: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload = place if isinstance(place, dict) else {}
    ctx = context if isinstance(context, dict) else {}

    place_name = str(payload.get("name") or "Nearby place").strip() or "Nearby place"
    menu_items = _extract_menu_items(payload)

    typical = _infer_typical_order(payload, menu_items)
    smart = _infer_smarter_order(payload, menu_items, recommended_order or {}, ctx)

    typical_cal = int(max(120, _safe_int(typical.get("estimated_calories"), 860)))
    typical_protein = int(max(6, _safe_int(typical.get("estimated_protein_g"), 26)))
    smart_cal = int(max(120, _safe_int(smart.get("estimated_calories"), 560)))
    smart_protein = int(max(6, _safe_int(smart.get("estimated_protein_g"), 34)))

    calories_saved = int(max(0, typical_cal - smart_cal))
    protein_diff = int(smart_protein - typical_protein)

    typical_conf = float(_safe_float(typical.get("confidence"), 0.56))
    smart_conf = float(_safe_float(smart.get("confidence"), 0.6))
    density_bonus = 0.08 if menu_items else 0.0
    confidence = _clamp((typical_conf * 0.5) + (smart_conf * 0.5) + density_bonus, 0.38, 0.94)

    short_reason = _build_short_reason(calories_saved, protein_diff)
    recommendation_source = str(
        (recommended_order or {}).get("menu_item_source")
        or ((ctx.get("top_menu_item") if isinstance(ctx.get("top_menu_item"), dict) else {}).get("menu_item_source"))
        or "heuristic"
    ).strip().lower()
    ctx_top_menu_item = ctx.get("top_menu_item") if isinstance(ctx.get("top_menu_item"), dict) else {}
    recommendation_confidence = float(
        _safe_float(
            (recommended_order or {}).get("menu_item_confidence"),
            _safe_float(ctx_top_menu_item.get("menu_item_confidence"), confidence),
        )
    )
    rewritten = maybe_rewrite_explanation_copy(
        place_name=place_name,
        cuisine=_place_text(payload),
        recommended_order=smart.get("name"),
        estimated_calories=smart_cal,
        estimated_protein_g=smart_protein,
        typical_order_calories=typical_cal,
        goal=ctx.get("goal"),
        confidence=confidence,
        recommendation_source=recommendation_source,
        menu_item_confidence=recommendation_confidence,
        today_fit=ctx.get("fit_for_today"),
        has_reality_check=True,
        base_why_this_works=short_reason,
        base_short_reason=short_reason,
    )
    short_reason = str(rewritten.get("short_reason") or short_reason)
    why_this_works = str(rewritten.get("why_this_works") or short_reason)
    copy_method = str(rewritten.get("copy_method") or "deterministic")
    copy_confidence = round(_clamp(_safe_float(rewritten.get("copy_confidence"), confidence), 0.2, 0.95), 2)
    copy_version = str(rewritten.get("copy_version") or "v1")

    reality_check = {
        "title": "Restaurant Reality Check",
        "place_name": _clip(place_name, 40, "Nearby place"),
        "typical_order": {
            "name": _clip(typical.get("name"), 72, "Typical combo meal"),
            "estimated_calories": typical_cal,
            "estimated_protein_g": typical_protein,
        },
        "smarter_order": {
            "name": _clip(smart.get("name"), 72, "Lighter menu option"),
            "estimated_calories": smart_cal,
            "estimated_protein_g": smart_protein,
        },
        "calories_saved": calories_saved,
        "protein_difference_g": protein_diff,
        "wow_line": f"You saved {calories_saved} calories." if calories_saved > 0 else "Smarter order for better control.",
        "why_this_works": why_this_works,
        "short_reason": short_reason,
        "confidence": round(float(confidence), 2),
        "copy_method": copy_method,
        "copy_confidence": copy_confidence,
        "copy_version": copy_version,
        "reality_check_version": RESTAURANT_REALITY_CHECK_VERSION,
    }

    reality_check["share_card"] = build_reality_check_share_card(
        place_name=reality_check["place_name"],
        typical_calories=typical_cal,
        smarter_calories=smart_cal,
        calories_saved=calories_saved,
        smarter_order=reality_check["smarter_order"]["name"],
        protein_difference_g=protein_diff,
    )

    return reality_check
