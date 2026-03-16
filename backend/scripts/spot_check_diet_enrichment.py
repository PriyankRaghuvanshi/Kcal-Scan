#!/usr/bin/env python3
"""
Diet-aware enrichment spot checks: 5 manual checks across McDonald's, Wow! Momo,
Haldiram's, Nando's, KFC. Run from backend with Supabase env for live data.

  cd backend && python3 scripts/spot_check_diet_enrichment.py
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


PLACES = [
    ("McDonald's (AU) – vegetarian", {"place_id": "spot_mcd_au", "place_name": "McDonald's – George Street", "name": "McDonald's – George Street", "lat": -33.8688, "lng": 151.2093, "vicinity": "Sydney, NSW, Australia", "country_code": "AU"}, "AU", "vegetarian"),
    ("Wow! Momo (IN) – vegetarian", {"place_id": "spot_wow_in", "place_name": "Wow! Momo – Indiranagar", "name": "Wow! Momo – Indiranagar", "lat": 12.9716, "lng": 77.5946, "vicinity": "Bengaluru, India", "country_code": "IN"}, "IN", "vegetarian"),
    ("Haldiram's (IN) – vegetarian", {"place_id": "spot_hr_in", "place_name": "Haldiram's – Connaught Place", "name": "Haldiram's – Connaught Place", "lat": 28.6139, "lng": 77.2090, "vicinity": "New Delhi, India", "country_code": "IN"}, "IN", "vegetarian"),
    ("Nando's (AU) – vegan", {"place_id": "spot_nandos_au", "place_name": "Nando's – Parramatta", "name": "Nando's – Parramatta", "lat": -33.8150, "lng": 150.9929, "vicinity": "Parramatta, NSW, Australia", "country_code": "AU"}, "AU", "vegan"),
    ("KFC (AU) – vegan", {"place_id": "spot_kfc_au", "place_name": "KFC – George Street", "name": "KFC – George Street", "lat": -33.8688, "lng": 151.2093, "vicinity": "Sydney, NSW, Australia", "country_code": "AU"}, "AU", "vegan"),
]


def main() -> None:
    print("=== Diet-aware enrichment spot checks ===\n")
    for label, place, market, diet in PLACES:
        print(f"--- {label} ---")
        enriched = enrich_place_with_local_profile(place.copy(), market_tag=market, diet_preference=diet)
        if enriched is None:
            print("Enriched: None")
        else:
            print("matched_chain_key:", enriched.get("matched_chain_key"))
            print("chain_menu_store:", enriched.get("chain_menu_store"))
            print("diet_filter_applied:", enriched.get("diet_filter_applied"))
            print("no_diet_safe_candidates:", enriched.get("no_diet_safe_candidates"))
            top = enriched.get("top_menu_item")
            if top is None:
                print("top_menu_item: None")
            else:
                print("top_menu_item:", json.dumps({"item_name": top.get("item_name"), "vegetarian_possible": top.get("vegetarian_possible"), "vegan_possible": top.get("vegan_possible")}, default=str))
        print()
    print("Done.")


if __name__ == "__main__":
    main()
