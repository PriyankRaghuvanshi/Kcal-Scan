#!/usr/bin/env python3
"""
Focused enrichment verification for Red Rooster (AU) and Hungry Jack's (AU).
Prints only: matched_chain_key, chain_menu_store, top_menu_item.

Run from backend (with Supabase env if using real DB):
  cd backend && python3 scripts/verify_enrichment_red_rooster_hungry_jacks_au.py
"""
from __future__ import annotations

import json
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

from local_venue_enrichment import enrich_place_with_local_profile


RED_ROOSTER_PLACE = {
    "place_id": "verify_red_rooster_au_001",
    "place_name": "Red Rooster – Parramatta",
    "name": "Red Rooster – Parramatta",
    "lat": -33.8150,
    "lng": 150.9929,
    "vicinity": "Parramatta, NSW, Australia",
    "country_code": "AU",
}

HUNGRY_JACKS_PLACE = {
    "place_id": "verify_hungry_jacks_au_001",
    "place_name": "Hungry Jack's – George Street",
    "name": "Hungry Jack's – George Street",
    "lat": -33.8688,
    "lng": 151.2093,
    "vicinity": "Sydney, NSW, Australia",
    "country_code": "AU",
}


def main() -> None:
    print("=== Red Rooster (AU) ===\n")
    enriched_r = enrich_place_with_local_profile(RED_ROOSTER_PLACE.copy(), market_tag="AU")
    if enriched_r is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_r.get("matched_chain_key"))
        print("chain_menu_store:", enriched_r.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_r.get("top_menu_item"), indent=2, default=str))
        print()

    print("=== Hungry Jack's (AU) ===\n")
    enriched_h = enrich_place_with_local_profile(HUNGRY_JACKS_PLACE.copy(), market_tag="AU")
    if enriched_h is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_h.get("matched_chain_key"))
        print("chain_menu_store:", enriched_h.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_h.get("top_menu_item"), indent=2, default=str))


if __name__ == "__main__":
    main()
