from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple

from menu_intelligence_store import MENU_INTELLIGENCE_VERSION
from menu_item_scoring import score_menu_item
from nutrition_mode import NutritionMode
from recommendation_safety import has_strong_menu_evidence, sanitize_recommended_item
from restaurant_macro_estimator import estimate_restaurant_macros


DEFAULT_STORE_PATH = Path(__file__).resolve().parent / "data" / "menu_intelligence_store.json"

STORE_SOURCE_DEFAULTS: Dict[str, float] = {
    "website_menu": 0.88,
    "scraped_menu": 0.72,
    "website_text": 0.74,
    "review_text": 0.60,
    "ocr_menu": 0.64,
    "user_scan": 0.82,
    "llm_inferred": 0.60,
    "heuristic_generation": 0.48,
}

SOURCE_RANK_WEIGHTS: Dict[str, float] = {
    "real_menu": 1.00,
    "user_scan": 0.95,
    "llm_inferred": 0.80,
    "heuristic": 0.65,
}

SOURCE_PRIORITY: Dict[str, int] = {
    "real_menu": 4,
    "user_scan": 3,
    "llm_inferred": 2,
    "heuristic": 1,
}

REAL_MENU_SOURCES = {
    "website_menu",
    "scraped_menu",
    "website_text",
    "review_text",
    "ocr_menu",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, float(value)))


def _norm(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _load_store(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"version": MENU_INTELLIGENCE_VERSION, "places": {}}
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if isinstance(data, dict):
            places = data.get("places")
            if isinstance(places, dict):
                return data
    except Exception:
        pass
    return {"version": MENU_INTELLIGENCE_VERSION, "places": {}}


def _save_store(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=True, indent=2, sort_keys=True)


def _menu_item_source(store_source: str, menu_item_source: Any = "") -> str:
    token = _norm(menu_item_source)
    if token in {"real_menu", "user_scan", "llm_inferred", "heuristic"}:
        return token
    src = _norm(store_source)
    if src == "user_scan":
        return "user_scan"
    if src == "llm_inferred":
        return "llm_inferred"
    if src in REAL_MENU_SOURCES:
        return "real_menu"
    return "heuristic"


def _store_source_for_menu_item(menu_item_source: str, current_source: str) -> str:
    token = _norm(menu_item_source)
    current = _norm(current_source)
    if token == "real_menu":
        return current if current in REAL_MENU_SOURCES else "scraped_menu"
    if token == "user_scan":
        return "user_scan"
    if token == "llm_inferred":
        return "llm_inferred"
    return "heuristic_generation"


def _source_confidence_default(source: str) -> float:
    return float(STORE_SOURCE_DEFAULTS.get(_norm(source), 0.48))


def _source_confidence_cap(menu_item_source: str) -> float:
    token = _norm(menu_item_source)
    if token == "real_menu":
        return 0.95
    if token == "user_scan":
        return 0.92
    if token == "llm_inferred":
        return 0.82
    return 0.62


def _coerce_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _item_context(place: Dict[str, Any]) -> str:
    return " ".join(
        [
            str(place.get("restaurant_name") or ""),
            str(place.get("cuisine") or ""),
            str(place.get("place_id") or ""),
        ]
    ).strip()


def _macro_backfill(
    *,
    item_name: str,
    place: Dict[str, Any],
    calories: int,
    protein: int,
    carbs: int,
    fat: int,
    satiety: str,
) -> Tuple[int, int, int, int, str]:
    if calories > 0 and protein > 0 and carbs >= 0 and fat >= 0 and satiety in {"high", "medium", "low"}:
        return calories, protein, carbs, fat, satiety

    estimate = estimate_restaurant_macros(
        item_name=item_name,
        cuisine_hint=_item_context(place),
        place={
            "name": str(place.get("restaurant_name") or ""),
            "types": [str(place.get("cuisine") or "")],
            "vicinity": "",
        },
        input_calories=calories if calories > 0 else None,
        input_protein_g=protein if protein > 0 else None,
    )

    est_cal = _safe_int(estimate.get("estimated_calories"), 520)
    est_protein = _safe_int(estimate.get("estimated_protein_g"), 28)
    est_carbs = _safe_int(estimate.get("estimated_carbs_g"), 46)
    est_fat = _safe_int(estimate.get("estimated_fat_g"), 18)
    est_satiety = str(estimate.get("estimated_satiety") or "").strip().lower()

    calories = calories if calories > 0 else max(120, est_cal)
    protein = protein if protein > 0 else max(6, est_protein)
    carbs = carbs if carbs > 0 else max(0, est_carbs)
    fat = fat if fat > 0 else max(0, est_fat)
    satiety = satiety if satiety in {"high", "medium", "low"} else (est_satiety if est_satiety in {"high", "medium", "low"} else "medium")
    return calories, protein, carbs, fat, satiety


def _scored_backfill_item(
    *,
    item: Dict[str, Any],
    place: Dict[str, Any],
    store_source: str,
    menu_item_source: str,
    confidence: float,
) -> Dict[str, Any]:
    context_text = _item_context(place)
    score_input = {
        "item_name": item["item_name"],
        "estimated_calories": item["estimated_calories"],
        "estimated_protein_g": item["estimated_protein_g"],
        "estimated_carbs_g": item["estimated_carbs_g"],
        "estimated_fat_g": item["estimated_fat_g"],
        "estimated_satiety": item["estimated_satiety"],
        "confidence": confidence,
        "menu_confidence": confidence,
        "source": store_source,
        "menu_source": store_source,
        "menu_item_source": menu_item_source,
        "source_url": item.get("source_url") or "",
        "extraction_method": item.get("extraction_method") or "",
        "parse_method": item.get("parse_method") or "",
        "raw_text_snippet": item.get("raw_text_snippet") or "",
        "category": item.get("category") or "",
        "likely_protein": item.get("likely_protein") or "",
        "likely_carbs": _coerce_list(item.get("likely_carbs")),
        "likely_fats": _coerce_list(item.get("likely_fats")),
        "health_signals": _coerce_list(item.get("health_signals")),
    }
    scored = score_menu_item(
        score_input,
        context={
            "menu_source": store_source,
            "cuisine_hint": context_text,
            "place_text": context_text,
            "place": {
                "name": str(place.get("restaurant_name") or ""),
                "types": [str(place.get("cuisine") or "")],
            },
        },
        mode=NutritionMode.DEFAULT,
    )
    return scored if isinstance(scored, dict) else {}


def _clean_item(
    item: Dict[str, Any],
    *,
    place: Dict[str, Any],
    now_iso: str,
) -> Tuple[Dict[str, Any] | None, bool]:
    if not isinstance(item, dict):
        return None, False
    original = dict(item)
    item_name = str(item.get("item_name") or item.get("name") or "").strip()
    if not item_name:
        return None, False

    store_source = _norm(item.get("source") or item.get("menu_source") or "heuristic_generation")
    if not store_source:
        store_source = "heuristic_generation"
    menu_source = _menu_item_source(store_source, item.get("menu_item_source"))

    confidence = _safe_float(
        item.get("menu_item_confidence"),
        _safe_float(item.get("menu_confidence"), _safe_float(item.get("confidence"), _source_confidence_default(store_source))),
    )
    confidence = _clamp(confidence, 0.2, _source_confidence_cap(menu_source))

    strong_menu_evidence = has_strong_menu_evidence(
        menu_item_source=menu_source,
        menu_item_confidence=confidence,
        source_url=item.get("source_url"),
        extraction_method=item.get("extraction_method"),
        parse_method=item.get("parse_method"),
        raw_text_snippet=item.get("raw_text_snippet"),
    )
    safety = sanitize_recommended_item(
        item_name=item_name,
        context_text=_item_context(place),
        menu_item_source=menu_source,
        menu_item_confidence=confidence,
        strong_menu_evidence=strong_menu_evidence,
        display_label=item.get("display_label"),
        order_type=item.get("order_type"),
    )

    cleaned_name = str(safety.get("item_name") or item_name).strip() or "Suggested lighter option"
    menu_source = str(safety.get("menu_item_source") or menu_source).strip().lower() or "heuristic"
    confidence = _clamp(_safe_float(safety.get("menu_item_confidence"), confidence), 0.2, _source_confidence_cap(menu_source))
    store_source = _store_source_for_menu_item(menu_source, store_source)

    est = item.get("estimated_macros") if isinstance(item.get("estimated_macros"), dict) else {}
    calories = _safe_int(item.get("estimated_calories"), _safe_int(est.get("calories"), 0))
    protein = _safe_int(item.get("estimated_protein_g"), _safe_int(est.get("protein_g"), 0))
    carbs = _safe_int(item.get("estimated_carbs_g"), _safe_int(est.get("carbs_g"), 0))
    fat = _safe_int(item.get("estimated_fat_g"), _safe_int(est.get("fat_g"), 0))
    satiety = str(item.get("estimated_satiety") or "").strip().lower()
    calories, protein, carbs, fat, satiety = _macro_backfill(
        item_name=cleaned_name,
        place=place,
        calories=calories,
        protein=protein,
        carbs=carbs,
        fat=fat,
        satiety=satiety,
    )

    cleaned: Dict[str, Any] = {
        "item_name": cleaned_name,
        "estimated_calories": int(max(0, calories)),
        "estimated_protein_g": int(max(0, protein)),
        "estimated_carbs_g": int(max(0, carbs)),
        "estimated_fat_g": int(max(0, fat)),
        "estimated_satiety": satiety if satiety in {"high", "medium", "low"} else "medium",
        "estimated_macros": {
            "calories": int(max(0, calories)),
            "protein_g": int(max(0, protein)),
            "carbs_g": int(max(0, carbs)),
            "fat_g": int(max(0, fat)),
        },
        "source": store_source,
        "menu_source": store_source,
        "confidence": round(confidence, 2),
        "menu_confidence": round(confidence, 2),
        "source_url": str(item.get("source_url") or "").strip(),
        "extraction_method": str(item.get("extraction_method") or "").strip(),
        "parse_method": str(item.get("parse_method") or "").strip(),
        "parsed_via": str(item.get("parsed_via") or "").strip(),
        "raw_text_snippet": str(item.get("raw_text_snippet") or "").strip()[:180],
        "category": str(item.get("category") or "").strip(),
        "likely_protein": str(item.get("likely_protein") or "").strip(),
        "likely_carbs": _coerce_list(item.get("likely_carbs")),
        "likely_fats": _coerce_list(item.get("likely_fats")),
        "health_signals": _coerce_list(item.get("health_signals")),
    }

    scored = _scored_backfill_item(
        item=cleaned,
        place=place,
        store_source=store_source,
        menu_item_source=menu_source,
        confidence=confidence,
    )
    scored_menu_source = str(scored.get("menu_item_source") or menu_source).strip().lower() or "heuristic"
    confidence = _clamp(_safe_float(scored.get("menu_item_confidence"), confidence), 0.2, _source_confidence_cap(scored_menu_source))
    store_source = _store_source_for_menu_item(scored_menu_source, store_source)

    cleaned.update(
        {
            "source": store_source,
            "menu_source": store_source,
            "confidence": round(confidence, 2),
            "menu_confidence": round(confidence, 2),
            "menu_item_source": scored_menu_source,
            "menu_item_confidence": round(confidence, 2),
            "display_label": str(scored.get("display_label") or safety.get("display_label") or "Suggested Lighter Option"),
            "source_rank_weight": round(
                _clamp(_safe_float(scored.get("source_rank_weight"), SOURCE_RANK_WEIGHTS.get(scored_menu_source, 0.65)), 0.5, 1.0),
                2,
            ),
            "source_priority": int(SOURCE_PRIORITY.get(scored_menu_source, 1)),
            "item_score": int(_safe_int(scored.get("item_score"), 0)),
            "rank_adjusted_item_score": int(_safe_int(scored.get("rank_adjusted_item_score"), _safe_int(scored.get("item_score"), 0))),
            "item_score_breakdown": scored.get("item_score_breakdown") if isinstance(scored.get("item_score_breakdown"), dict) else {},
            "order_type": str(scored.get("order_type") or safety.get("order_type") or "estimated"),
            "menu_item_safety_reason": str(safety.get("safety_reason") or ""),
            "last_updated": now_iso,
        }
    )

    downgraded = False
    if SOURCE_PRIORITY.get(scored_menu_source, 1) < SOURCE_PRIORITY.get(_menu_item_source(_norm(original.get("source") or original.get("menu_source") or ""), original.get("menu_item_source")), 1):
        downgraded = True
    if str(safety.get("safety_reason") or "").strip():
        downgraded = True
    if round(_safe_float(original.get("confidence"), confidence), 2) - confidence > 0.06:
        downgraded = True
    return cleaned, downgraded


def cleanup_menu_intelligence_store(path: str | Path | None = None, *, dry_run: bool = False) -> Dict[str, Any]:
    store_path = Path(path) if path else DEFAULT_STORE_PATH
    store = _load_store(store_path)
    places = store.get("places") if isinstance(store.get("places"), dict) else {}
    now_iso = _now_iso()

    report: Dict[str, Any] = {
        "path": str(store_path),
        "places_total": 0,
        "places_removed": 0,
        "rows_total": 0,
        "removed_rows": 0,
        "downgraded_rows": 0,
        "backfilled_rows": 0,
        "preserved_rows": 0,
    }

    cleaned_places: Dict[str, Any] = {}
    for place_id, place_raw in places.items():
        if not isinstance(place_raw, dict):
            continue
        report["places_total"] += 1
        place = dict(place_raw)
        place["place_id"] = str(place.get("place_id") or place_id).strip()
        place["restaurant_name"] = str(place.get("restaurant_name") or "").strip()
        place["cuisine"] = str(place.get("cuisine") or "").strip()

        original_items = place.get("menu_items") if isinstance(place.get("menu_items"), list) else []
        cleaned_items: List[Dict[str, Any]] = []
        place_changed = False

        for item_raw in original_items:
            report["rows_total"] += 1
            cleaned_item, downgraded = _clean_item(item_raw, place=place, now_iso=now_iso)
            if cleaned_item is None:
                report["removed_rows"] += 1
                place_changed = True
                continue

            if item_raw != cleaned_item:
                place_changed = True
                if downgraded:
                    report["downgraded_rows"] += 1
                else:
                    report["backfilled_rows"] += 1
            else:
                report["preserved_rows"] += 1
            cleaned_items.append(cleaned_item)

        if not cleaned_items:
            report["places_removed"] += 1
            continue

        cleaned_items.sort(
            key=lambda row: (
                int(_safe_int(row.get("rank_adjusted_item_score"), 0)),
                int(_safe_int(row.get("source_priority"), 0)),
                str(row.get("item_name") or "").lower(),
            ),
            reverse=True,
        )

        sources_ordered: List[str] = []
        for row in cleaned_items:
            src = str(row.get("source") or row.get("menu_source") or "heuristic_generation").strip().lower()
            if src and src not in sources_ordered:
                sources_ordered.append(src)

        if not isinstance(place.get("sources"), list) or place_changed:
            place["sources"] = sources_ordered

        place["menu_items"] = cleaned_items
        place["confidence"] = round(
            _clamp(
                max([_safe_float(r.get("menu_item_confidence"), _safe_float(r.get("confidence"), 0.0)) for r in cleaned_items] or [0.0]),
                0.1,
                0.99,
            ),
            2,
        )
        place["last_updated"] = now_iso if place_changed else str(place.get("last_updated") or now_iso)
        place["version"] = MENU_INTELLIGENCE_VERSION
        cleaned_places[str(place_id)] = place

    cleaned_store = {
        "version": MENU_INTELLIGENCE_VERSION,
        "places": cleaned_places,
    }
    if not dry_run:
        _save_store(store_path, cleaned_store)

    return report


def _main() -> int:
    parser = argparse.ArgumentParser(description="Clean and backfill menu intelligence store entries.")
    parser.add_argument("--path", default=str(DEFAULT_STORE_PATH), help="Path to menu intelligence store JSON")
    parser.add_argument("--dry-run", action="store_true", help="Run cleanup without writing changes")
    args = parser.parse_args()

    report = cleanup_menu_intelligence_store(args.path, dry_run=bool(args.dry_run))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
