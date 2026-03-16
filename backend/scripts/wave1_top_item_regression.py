#!/usr/bin/env python3
"""
Wave 1 top-item regression: enrich one mock place per chain and assert expected top item.
Fails if matched_chain_key, chain_menu_store, or top item name is wrong.
Run from backend (with Supabase env): python3 scripts/wave1_top_item_regression.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

for _env in (BACKEND / ".env", BACKEND.parent / ".env"):
    if _env.exists():
        with _env.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break

# (place_name, market_tag, expected_chain_key, expected_top_contains) - at least one substring
WAVE1_CHECKS = [
    ("Chipotle Mexican Grill – SoMa", "US", "chipotle", ["High Protein Bowl", "Green Goddess"]),
    ("Taco Bell – Times Square", "US", "taco_bell", ["Power Menu Bowl"]),
    ("Panera Bread Bakery Cafe", "US", "panera", ["Green Goddess", "Caesar Salad"]),
    ("Faasos by EatSure – Indiranagar", "IN", "faasos", ["High Protein Chicken Wrap"]),
    ("Wow! Momo – Salt Lake", "IN", "wow_momo", ["Steamed", "Grilled", "Chicken Momo", "Momo Bowl"]),
    ("Haldiram's Restaurant", "IN", "haldirams", ["Tandoori Chicken", "Paneer Tikka"]),
    ("Barbeque Nation – Indiranagar", "IN", "barbeque_nation", ["Tandoori", "Grilled Chicken", "Grilled Fish", "Seekh"]),
]


def _place(name: str, market: str) -> dict:
    return {
        "place_id": f"wave1_regress_{market.lower()}",
        "place_name": name,
        "name": name,
        "vicinity": "India" if market == "IN" else "USA",
        "country_code": market,
    }


def main() -> None:
    from local_venue_enrichment import enrich_place_with_local_profile
    failed = []
    for place_name, market_tag, expected_chain, expected_top_contains in WAVE1_CHECKS:
        place = _place(place_name, market_tag)
        enriched = enrich_place_with_local_profile(place, market_tag=market_tag)
        if enriched is None:
            failed.append((expected_chain, "Enriched is None"))
            continue
        if enriched.get("matched_chain_key") != expected_chain:
            failed.append((expected_chain, f"matched_chain_key={enriched.get('matched_chain_key')}"))
            continue
        if enriched.get("chain_menu_store") != "supabase":
            failed.append((expected_chain, f"chain_menu_store={enriched.get('chain_menu_store')}"))
            continue
        top = enriched.get("top_menu_item") or {}
        top_name = (top.get("item_name") or "").strip()
        if not any(sub in top_name for sub in expected_top_contains):
            failed.append((expected_chain, f"top_menu_item name '{top_name}' not in {expected_top_contains}"))
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("Wave 1 top-item regression: all 7 chains OK")


if __name__ == "__main__":
    main()
