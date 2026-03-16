#!/usr/bin/env python3
"""
Focused enrichment verification for Barbeque Nation (IN).
Prints only: matched_chain_key, chain_menu_store, top_menu_item.
Conservative rollout: top item should be grilled/skewer/protein-forward, not buffet/heavy.

Run from backend (with Supabase env if using real DB):
  cd backend && python3 scripts/verify_enrichment_barbeque_nation.py
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


BARBEQUE_NATION_PLACE = {
    "place_id": "verify_bbqn_001",
    "place_name": "Barbeque Nation – Indiranagar",
    "name": "Barbeque Nation – Indiranagar",
    "lat": 12.9716,
    "lng": 77.5946,
    "vicinity": "Bengaluru, India",
    "country_code": "IN",
}


def main() -> None:
    print("=== Barbeque Nation (IN) ===\n")
    enriched = enrich_place_with_local_profile(BARBEQUE_NATION_PLACE.copy(), market_tag="IN")
    if enriched is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched.get("matched_chain_key"))
        print("chain_menu_store:", enriched.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched.get("top_menu_item"), indent=2, default=str))


if __name__ == "__main__":
    main()
