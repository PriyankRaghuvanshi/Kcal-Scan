from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Tuple


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from chain_menu_registry import list_chain_entries, resolve_chain_menu_for_place  # noqa: E402
from menu_intelligence_store import SOURCE_WEBSITE_MENU, ingest_menu_intelligence  # noqa: E402


def _store_path() -> Path:
    override = str(os.getenv("MENU_INTELLIGENCE_STORE_PATH") or "").strip()
    if override:
        return Path(override)
    return BACKEND_DIR / "data" / "menu_intelligence_store.json"


def _load_store_places(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except Exception:
        return {}
    places = payload.get("places") if isinstance(payload, dict) else {}
    if not isinstance(places, dict):
        return {}
    return {str(k): v for k, v in places.items() if isinstance(v, dict)}


def _ingest_chain_entry(chain: Dict[str, Any], max_items: int) -> Tuple[bool, int]:
    chain_name = str(chain.get("chain_name") or "").strip()
    if not chain_name:
        return False, 0

    bundle = resolve_chain_menu_for_place(
        {"name": chain_name, "country_code": chain.get("country_code")},
        country_code=str(chain.get("country_code") or ""),
        max_items=max_items,
    )
    items = bundle.get("menu_items") if isinstance(bundle.get("menu_items"), list) else []
    if not items:
        return False, 0

    place_id = f"chain::{str(chain.get('chain_id') or chain_name).strip().lower()}"
    entry = ingest_menu_intelligence(
        place_id=place_id,
        restaurant_name=chain_name,
        cuisine=str(chain.get("chain_key") or "chain").replace("_", " "),
        menu_items=items,
        source=SOURCE_WEBSITE_MENU,
    )
    return bool(isinstance(entry, dict)), len(items)


def _backfill_existing_place_ids(country_code: str, max_items: int) -> Tuple[int, int]:
    places = _load_store_places(_store_path())
    matched = 0
    updated = 0

    for place_id, entry in places.items():
        place_name = str(entry.get("restaurant_name") or "").strip()
        if not place_name:
            continue

        bundle = resolve_chain_menu_for_place(
            {
                "name": place_name,
                "country_code": country_code,
                "address": str(entry.get("cuisine") or ""),
            },
            country_code=country_code,
            max_items=max_items,
        )
        items = bundle.get("menu_items") if isinstance(bundle.get("menu_items"), list) else []
        if not items:
            continue

        matched += 1
        out = ingest_menu_intelligence(
            place_id=place_id,
            restaurant_name=place_name,
            cuisine=str(entry.get("cuisine") or ""),
            menu_items=items,
            source=SOURCE_WEBSITE_MENU,
        )
        if isinstance(out, dict):
            updated += 1

    return matched, updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill chain menu intelligence from registry coverage")
    parser.add_argument("--country", default="AU", help="Country code (default: AU)")
    parser.add_argument("--max-items", type=int, default=12, help="Max menu items per chain")
    parser.add_argument(
        "--include-existing-place-ids",
        action="store_true",
        help="Also backfill existing place_ids in menu_intelligence_store if their names match a chain",
    )
    args = parser.parse_args()

    country_code = str(args.country or "AU").strip().upper()
    max_items = max(1, min(30, int(args.max_items or 12)))

    chains = list_chain_entries(country_code=country_code, include_global=False)
    seeded = 0
    seeded_items = 0

    for chain in chains:
        ok, item_count = _ingest_chain_entry(chain, max_items=max_items)
        if ok:
            seeded += 1
            seeded_items += item_count

    matched_existing = 0
    updated_existing = 0
    if args.include_existing_place_ids:
        matched_existing, updated_existing = _backfill_existing_place_ids(country_code=country_code, max_items=max_items)

    print(
        json.dumps(
            {
                "country_code": country_code,
                "chains_seeded": seeded,
                "chain_items_seeded": seeded_items,
                "existing_places_matched": matched_existing,
                "existing_places_updated": updated_existing,
                "status": "ok",
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
