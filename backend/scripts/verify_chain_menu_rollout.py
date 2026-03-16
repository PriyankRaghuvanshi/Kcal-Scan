#!/usr/bin/env python3
"""
Chain menu rollout verification: sync, status, and enrichment.
Run from repo root: python3 backend/scripts/verify_chain_menu_rollout.py
Or from backend: python3 scripts/verify_chain_menu_rollout.py
Paste the output for a quick rollout check.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Run from backend so imports work
BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

def main() -> None:
    print("=== 1) Seed files ===")
    for name in ("chipotle_us.json", "faasos_in.json"):
        path = BACKEND / "data" / "chains" / name
        exists = path.exists()
        print(f"  {path.name}: {'present' if exists else 'MISSING'}")

    print("\n=== 2) Sync (Python) ===")
    from chain_menu_supabase_sync import sync_chain_menu_to_supabase
    chipotle_sync = sync_chain_menu_to_supabase("chipotle", "US")
    faasos_sync = sync_chain_menu_to_supabase("faasos", "IN")
    print("  chipotle US:", json.dumps(chipotle_sync))
    print("  faasos IN:", json.dumps(faasos_sync))

    print("\n=== 3) Status (if API available) ===")
    base_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    try:
        import urllib.request
        for market in ("US", "IN"):
            url = f"{base_url}/chain-menus/status?market_tag={market}"
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode())
                    print(f"  {market}:", json.dumps(data))
            except Exception as e:
                print(f"  {market}: (no endpoint or error) {e}")
    except Exception as e:
        print("  (skipped)", e)

    print("\n=== 4) Enrichment (Chipotle + Faasos) ===")
    from local_venue_enrichment import enrich_place_with_local_profile
    chipotle_place = {
        "place_id": "real_test_chipotle_001",
        "place_name": "Chipotle Mexican Grill – SoMa",
        "name": "Chipotle Mexican Grill – SoMa",
        "vicinity": "San Francisco, CA, USA",
        "country_code": "US",
        "lat": 37.7749,
        "lng": -122.4194,
    }
    faasos_place = {
        "place_id": "real_test_faasos_001",
        "place_name": "Faasos by EatSure – Indiranagar",
        "name": "Faasos by EatSure – Indiranagar",
        "vicinity": "Bengaluru, India",
        "country_code": "IN",
        "lat": 12.9716,
        "lng": 77.5946,
    }
    chipotle_enriched = enrich_place_with_local_profile(chipotle_place, market_tag="US")
    faasos_enriched = enrich_place_with_local_profile(faasos_place, market_tag="IN")
    print("  chipotle_enriched:")
    print(json.dumps(chipotle_enriched, indent=2, default=str) if chipotle_enriched else "    None")
    print("  faasos_enriched:")
    print(json.dumps(faasos_enriched, indent=2, default=str) if faasos_enriched else "    None")

    print("\n=== 5) Trace (if enrichment returned data) ===")
    try:
        from place_trace_debug import build_place_trace
        for label, enriched in (("chipotle_trace", chipotle_enriched), ("faasos_trace", faasos_enriched)):
            if enriched:
                trace = build_place_trace(enriched)
                print(f"  {label}:", json.dumps(trace, indent=2, default=str))
            else:
                print(f"  {label}: (no enriched payload)")
    except Exception as e:
        print("  (skipped)", e)


if __name__ == "__main__":
    main()
