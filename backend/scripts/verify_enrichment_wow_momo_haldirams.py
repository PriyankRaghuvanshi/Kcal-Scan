#!/usr/bin/env python3
"""
Focused enrichment verification for Wow! Momo (IN) and Haldiram's (IN).
Prints only: matched_chain_key, chain_menu_store, top_menu_item.

Run from backend (with Supabase env if using real DB):
  cd backend && python3 scripts/verify_enrichment_wow_momo_haldirams.py
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


def _mock_place(name: str, place_id: str, lat: float, lng: float, vicinity: str = "", country_code: str = "IN") -> dict:
    return {
        "place_id": place_id,
        "place_name": name,
        "name": name,
        "lat": lat,
        "lng": lng,
        "vicinity": vicinity,
        "country_code": country_code,
    }


WOW_MOMO_PLACE = _mock_place(
    "Wow! Momo – Salt Lake",
    "verify_wowmomo_001",
    22.5726,
    88.3639,
    "Kolkata, India",
)

HALDIRAMS_PLACE = _mock_place(
    "Haldiram's Restaurant",
    "verify_haldirams_001",
    28.6139,
    77.2090,
    "Delhi, India",
)


def main() -> None:
    print("=== Wow! Momo (IN) ===\n")
    enriched_wm = enrich_place_with_local_profile(WOW_MOMO_PLACE.copy(), market_tag="IN")
    if enriched_wm is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_wm.get("matched_chain_key"))
        print("chain_menu_store:", enriched_wm.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_wm.get("top_menu_item"), indent=2, default=str))
        print()

    print("=== Haldiram's (IN) ===\n")
    enriched_hr = enrich_place_with_local_profile(HALDIRAMS_PLACE.copy(), market_tag="IN")
    if enriched_hr is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_hr.get("matched_chain_key"))
        print("chain_menu_store:", enriched_hr.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_hr.get("top_menu_item"), indent=2, default=str))


if __name__ == "__main__":
    main()
