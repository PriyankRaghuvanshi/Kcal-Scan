#!/usr/bin/env python3
"""
Focused enrichment verification for Nando's (AU) and KFC (AU).
Prints only: matched_chain_key, chain_menu_store, top_menu_item.

Run from backend (with Supabase env if using real DB):
  cd backend && python3 scripts/verify_enrichment_nandos_kfc_au.py
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


NANDOS_PLACE = {
    "place_id": "verify_nandos_au_001",
    "place_name": "Nando's – Parramatta",
    "name": "Nando's – Parramatta",
    "lat": -33.8150,
    "lng": 150.9929,
    "vicinity": "Parramatta, NSW, Australia",
    "country_code": "AU",
}

KFC_PLACE = {
    "place_id": "verify_kfc_au_001",
    "place_name": "KFC – George Street",
    "name": "KFC – George Street",
    "lat": -33.8688,
    "lng": 151.2093,
    "vicinity": "Sydney, NSW, Australia",
    "country_code": "AU",
}


def main() -> None:
    print("=== Nando's (AU) ===\n")
    enriched_n = enrich_place_with_local_profile(NANDOS_PLACE.copy(), market_tag="AU")
    if enriched_n is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_n.get("matched_chain_key"))
        print("chain_menu_store:", enriched_n.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_n.get("top_menu_item"), indent=2, default=str))
        print()

    print("=== KFC (AU) ===\n")
    enriched_k = enrich_place_with_local_profile(KFC_PLACE.copy(), market_tag="AU")
    if enriched_k is None:
        print("Enriched: None\n")
    else:
        print("matched_chain_key:", enriched_k.get("matched_chain_key"))
        print("chain_menu_store:", enriched_k.get("chain_menu_store"))
        print("top_menu_item:", json.dumps(enriched_k.get("top_menu_item"), indent=2, default=str))


if __name__ == "__main__":
    main()
