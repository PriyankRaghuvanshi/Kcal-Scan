#!/usr/bin/env python3
"""
Focused enrichment verification for Taco Bell / US and Panera / US.
Prints only: matched_chain_key, chain_menu_store, top_menu_item.

Run from backend (with Supabase env if using real DB):
  cd backend && python3 scripts/verify_enrichment_taco_bell_panera.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# Optional: load .env so Supabase is available
for _env in (BACKEND / ".env", BACKEND.parent / ".env"):
    if _env.exists():
        with _env.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break

from local_venue_enrichment import enrich_place_with_local_profile


def _mock_place(name: str, place_id: str, lat: float, lng: float, vicinity: str = "") -> dict:
    return {
        "place_id": place_id,
        "place_name": name,
        "name": name,
        "lat": lat,
        "lng": lng,
        "vicinity": vicinity,
        "country_code": "US",
    }


TACO_BELL_PLACE = _mock_place(
    "Taco Bell – Times Square",
    "verify_tacobell_001",
    40.7580,
    -73.9855,
    "New York, NY",
)

PANERA_PLACE = _mock_place(
    "Panera Bread Bakery Cafe",
    "verify_panera_001",
    41.8781,
    -87.6298,
    "Chicago, IL",
)


def main() -> None:
    print("=== Taco Bell (US) ===\n")
    enriched_tb = enrich_place_with_local_profile(TACO_BELL_PLACE.copy(), market_tag="US")
    if enriched_tb is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_tb.get("matched_chain_key"))
        print("chain_menu_store:", enriched_tb.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_tb.get("top_menu_item"), indent=2, default=str))
        print()

    print("=== Panera (US) ===\n")
    enriched_pn = enrich_place_with_local_profile(PANERA_PLACE.copy(), market_tag="US")
    if enriched_pn is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_pn.get("matched_chain_key"))
        print("chain_menu_store:", enriched_pn.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_pn.get("top_menu_item"), indent=2, default=str))


if __name__ == "__main__":
    main()
