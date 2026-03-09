from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


MENU_INTELLIGENCE_VERSION = "v1"

SOURCE_SCRAPED_MENU = "scraped_menu"
SOURCE_HEURISTIC = "heuristic_generation"
SOURCE_USER_SCAN = "user_scan"
SOURCE_LLM_INFERRED = "llm_inferred"
SOURCE_WEBSITE_MENU = "website_menu"
SOURCE_WEBSITE_TEXT = "website_text"
SOURCE_REVIEW_TEXT = "review_text"
SOURCE_OCR_MENU = "ocr_menu"

_SOURCE_ALIASES = {
    "scraped_menu": SOURCE_SCRAPED_MENU,
    "scraped": SOURCE_SCRAPED_MENU,
    "menu_scrape": SOURCE_SCRAPED_MENU,
    "website_menu": SOURCE_WEBSITE_MENU,
    "website_text": SOURCE_WEBSITE_TEXT,
    "review_text": SOURCE_REVIEW_TEXT,
    "review": SOURCE_REVIEW_TEXT,
    "ocr_menu": SOURCE_OCR_MENU,
    "ocr_text": SOURCE_OCR_MENU,
    "heuristic": SOURCE_HEURISTIC,
    "heuristic_generation": SOURCE_HEURISTIC,
    "generated": SOURCE_HEURISTIC,
    "llm_inferred": SOURCE_LLM_INFERRED,
    "llm": SOURCE_LLM_INFERRED,
    "user_scan": SOURCE_USER_SCAN,
    "scan": SOURCE_USER_SCAN,
    "user": SOURCE_USER_SCAN,
}

_SOURCE_CONFIDENCE_DEFAULT = {
    SOURCE_SCRAPED_MENU: 0.72,
    SOURCE_WEBSITE_MENU: 0.88,
    SOURCE_WEBSITE_TEXT: 0.74,
    SOURCE_REVIEW_TEXT: 0.6,
    SOURCE_OCR_MENU: 0.64,
    SOURCE_HEURISTIC: 0.48,
    SOURCE_LLM_INFERRED: 0.6,
    SOURCE_USER_SCAN: 0.82,
}

_SOURCE_PRIORITY = {
    SOURCE_HEURISTIC: 1,
    SOURCE_LLM_INFERRED: 2,
    SOURCE_SCRAPED_MENU: 2,
    SOURCE_REVIEW_TEXT: 2,
    SOURCE_OCR_MENU: 2,
    SOURCE_WEBSITE_TEXT: 3,
    SOURCE_WEBSITE_MENU: 4,
    SOURCE_USER_SCAN: 3,
}

_SOURCE_RANK_WEIGHT = {
    SOURCE_HEURISTIC: 0.65,
    SOURCE_LLM_INFERRED: 0.80,
    SOURCE_SCRAPED_MENU: 1.00,
    SOURCE_REVIEW_TEXT: 1.00,
    SOURCE_OCR_MENU: 0.95,
    SOURCE_WEBSITE_TEXT: 1.00,
    SOURCE_WEBSITE_MENU: 1.00,
    SOURCE_USER_SCAN: 0.95,
}

_STORE_LOCK = threading.Lock()


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    override = str(os.getenv("MENU_INTELLIGENCE_STORE_PATH", "") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "menu_intelligence_store.json"


def _ensure_store_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return {"version": MENU_INTELLIGENCE_VERSION, "places": {}}
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("places"), dict):
            return data
    except Exception:
        pass
    return {"version": MENU_INTELLIGENCE_VERSION, "places": {}}


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    _ensure_store_dir(path)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def _normalize_source(source: Any) -> str:
    raw = str(source or "").strip().lower()
    return _SOURCE_ALIASES.get(raw, SOURCE_HEURISTIC)


def _normalize_item(item: Dict[str, Any], source: str) -> Dict[str, Any] | None:
    payload = item if isinstance(item, dict) else {}
    item_name = str(payload.get("item_name") or payload.get("name") or payload.get("title") or "").strip()
    if not item_name:
        return None

    item_source = _normalize_source(payload.get("source") or payload.get("menu_source") or source)
    estimated_macros = payload.get("estimated_macros") if isinstance(payload.get("estimated_macros"), dict) else {}

    calories = int(
        _safe_float(
            payload.get("estimated_calories", payload.get("calories", estimated_macros.get("calories", 0))),
            0,
        )
        or 0
    )
    protein = int(
        _safe_float(
            payload.get("estimated_protein_g", payload.get("protein_g", estimated_macros.get("protein_g", 0))),
            0,
        )
        or 0
    )
    carbs = int(
        _safe_float(
            payload.get("estimated_carbs_g", payload.get("carbs_g", estimated_macros.get("carbs_g", 0))),
            0,
        )
        or 0
    )
    fat = int(
        _safe_float(
            payload.get("estimated_fat_g", payload.get("fat_g", estimated_macros.get("fat_g", 0))),
            0,
        )
        or 0
    )
    satiety = str(payload.get("estimated_satiety") or "").strip().lower()
    confidence = float(
        _safe_float(
            payload.get("confidence"),
            _SOURCE_CONFIDENCE_DEFAULT.get(item_source, _SOURCE_CONFIDENCE_DEFAULT.get(source, 0.5)),
        )
        or _SOURCE_CONFIDENCE_DEFAULT.get(item_source, _SOURCE_CONFIDENCE_DEFAULT.get(source, 0.5))
    )
    confidence = max(0.1, min(0.99, confidence))

    return {
        "item_name": item_name,
        "estimated_calories": calories,
        "estimated_protein_g": protein,
        "estimated_carbs_g": carbs,
        "estimated_fat_g": fat,
        "estimated_satiety": satiety if satiety in {"high", "medium", "low"} else "",
        "estimated_macros": {
            "calories": calories,
            "protein_g": protein,
            "carbs_g": carbs,
            "fat_g": fat,
        },
        "confidence": round(confidence, 2),
        "source": item_source,
        "menu_source": item_source,
        "menu_item_source": str(payload.get("menu_item_source") or _SOURCE_ALIASES.get(item_source, item_source)).strip() or item_source,
        "menu_item_confidence": round(confidence, 2),
        "menu_confidence": round(confidence, 2),
        "source_priority": int(_SOURCE_PRIORITY.get(item_source, 1)),
        "source_rank_weight": round(float(_SOURCE_RANK_WEIGHT.get(item_source, 0.65)), 2),
        "source_url": str(payload.get("source_url") or "").strip(),
        "extraction_method": str(payload.get("extraction_method") or "").strip(),
        "parse_method": str(payload.get("parse_method") or "").strip(),
        "parsed_via": str(payload.get("parsed_via") or "").strip(),
        "raw_text_snippet": str(payload.get("raw_text_snippet") or "").strip()[:180],
        "category": str(payload.get("category") or "").strip(),
        "likely_protein": str(payload.get("likely_protein") or "").strip(),
        "likely_carbs": payload.get("likely_carbs") if isinstance(payload.get("likely_carbs"), list) else [],
        "likely_fats": payload.get("likely_fats") if isinstance(payload.get("likely_fats"), list) else [],
        "health_signals": payload.get("health_signals") if isinstance(payload.get("health_signals"), list) else [],
        "chain_id": str(payload.get("chain_id") or "").strip(),
        "chain_key": str(payload.get("chain_key") or "").strip(),
        "chain_name": str(payload.get("chain_name") or "").strip(),
        "canonical_name": str(payload.get("canonical_name") or payload.get("chain_name") or "").strip(),
        "chain_name_resolved": str(payload.get("chain_name_resolved") or payload.get("chain_name") or "").strip(),
        "country_code": str(payload.get("country_code") or "").strip().upper(),
        "matched_alias": str(payload.get("matched_alias") or "").strip(),
        "matched_place_name": str(payload.get("matched_place_name") or "").strip(),
        "chain_source_used": str(payload.get("chain_source_used") or "").strip(),
        "source_type": str(payload.get("source_type") or "").strip(),
        "official_menu_source_url": str(payload.get("official_menu_source_url") or "").strip(),
        "menu_last_updated": str(payload.get("menu_last_updated") or "").strip(),
        "chain_match_confidence": round(_safe_float(payload.get("chain_match_confidence"), 0.0), 2),
        "last_updated": _now_iso(),
    }


def _canonical_place_id(place_id: Any) -> str:
    return str(place_id or "").strip()


def _existing_idx_by_name(menu_items: List[Dict[str, Any]], item_name: str) -> int:
    target = " ".join(item_name.strip().lower().split())
    for idx, item in enumerate(menu_items):
        probe = " ".join(str(item.get("item_name") or "").strip().lower().split())
        if probe and probe == target:
            return idx
    return -1


def _merge_item(existing: Dict[str, Any], incoming: Dict[str, Any]) -> Dict[str, Any]:
    ex_source = str(existing.get("source") or SOURCE_HEURISTIC)
    in_source = str(incoming.get("source") or SOURCE_HEURISTIC)
    ex_pri = _SOURCE_PRIORITY.get(ex_source, 0)
    in_pri = _SOURCE_PRIORITY.get(in_source, 0)

    if in_pri > ex_pri:
        base = dict(incoming)
    else:
        base = dict(existing)
        for key in (
            "estimated_calories",
            "estimated_protein_g",
            "estimated_carbs_g",
            "estimated_fat_g",
            "estimated_satiety",
            "estimated_macros",
        ):
            if (not base.get(key)) and incoming.get(key):
                base[key] = incoming.get(key)
        base["confidence"] = round(
            max(
                float(_safe_float(base.get("confidence"), 0.0) or 0.0),
                float(_safe_float(incoming.get("confidence"), 0.0) or 0.0),
            ),
            2,
        )
        base["source"] = base.get("source") or incoming.get("source") or SOURCE_HEURISTIC

    base["last_updated"] = _now_iso()
    return base


def ingest_menu_intelligence(
    *,
    place_id: Any,
    restaurant_name: Any = "",
    cuisine: Any = "",
    menu_items: List[Dict[str, Any]] | None = None,
    source: Any = SOURCE_HEURISTIC,
) -> Dict[str, Any] | None:
    canonical_place_id = _canonical_place_id(place_id)
    if not canonical_place_id:
        return None

    normalized_source = _normalize_source(source)
    normalized_items: List[Dict[str, Any]] = []
    for item in (menu_items or []):
        normalized = _normalize_item(item if isinstance(item, dict) else {}, normalized_source)
        if normalized:
            normalized_items.append(normalized)

    with _STORE_LOCK:
        store = _load_store()
        places = store.setdefault("places", {})
        existing = places.get(canonical_place_id) if isinstance(places.get(canonical_place_id), dict) else {}
        existing_items = existing.get("menu_items") if isinstance(existing.get("menu_items"), list) else []

        merged_items = [dict(item) for item in existing_items]
        for incoming in normalized_items:
            idx = _existing_idx_by_name(merged_items, str(incoming.get("item_name") or ""))
            if idx >= 0:
                merged_items[idx] = _merge_item(merged_items[idx], incoming)
            else:
                merged_items.append(incoming)

        sources = existing.get("sources") if isinstance(existing.get("sources"), list) else []
        if normalized_source not in sources:
            sources.append(normalized_source)

        entry = {
            "place_id": canonical_place_id,
            "restaurant_name": str(restaurant_name or existing.get("restaurant_name") or "").strip(),
            "cuisine": str(cuisine or existing.get("cuisine") or "").strip(),
            "menu_items": merged_items,
            "confidence": round(
                max(
                    [float(_safe_float(item.get("confidence"), 0.0) or 0.0) for item in merged_items] + [0.0]
                ),
                2,
            ),
            "last_updated": _now_iso(),
            "sources": sources,
            "version": MENU_INTELLIGENCE_VERSION,
        }

        places[canonical_place_id] = entry
        store["version"] = MENU_INTELLIGENCE_VERSION
        _save_store(store)
        return entry


def get_place_menu_intelligence(place_id: Any) -> Dict[str, Any] | None:
    canonical_place_id = _canonical_place_id(place_id)
    if not canonical_place_id:
        return None
    with _STORE_LOCK:
        store = _load_store()
        places = store.get("places") if isinstance(store.get("places"), dict) else {}
        entry = places.get(canonical_place_id)
        return dict(entry) if isinstance(entry, dict) else None


def get_menu_items_by_place_id(place_id: Any) -> List[Dict[str, Any]]:
    entry = get_place_menu_intelligence(place_id)
    if not isinstance(entry, dict):
        return []
    items = entry.get("menu_items")
    if not isinstance(items, list):
        return []
    return [dict(item) for item in items if isinstance(item, dict)]
