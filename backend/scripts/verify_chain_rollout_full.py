#!/usr/bin/env python3
"""
Full chain rollout verification: sync Chipotle/Faasos, then enrichment + trace.
Run with Supabase env loaded so sync and enrichment hit the real DB.

  cd backend
  set -a && source .env && set +a   # or source ../mobile/.env if vars are there
  python3 scripts/verify_chain_rollout_full.py

Then paste: the two sync outputs, one chipotle_enriched, one faasos_enriched
(and optionally the two traces) for confirmation.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# Optional: load .env from backend or project root
for _env in (BACKEND / ".env", BACKEND.parent / ".env", BACKEND.parent / "mobile" / ".env"):
    if _env.exists():
        with _env.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    os.environ.setdefault(k, v)
        break

def main():
    print("=== 1) Real sync ===")
    from chain_menu_supabase_sync import sync_chain_menu_to_supabase
    c = sync_chain_menu_to_supabase("chipotle", "US")
    f = sync_chain_menu_to_supabase("faasos", "IN")
    print("chipotle US:", json.dumps(c))
    print("faasos IN:", json.dumps(f))

    print("\n=== 2) Verify rows in Supabase (run in SQL Editor) ===")
    print("""
select chain_key, market_tag, item_key, item_name
from public.chain_menu_items
where chain_key in ('chipotle', 'faasos')
order by chain_key, market_tag, item_key;
""")

    print("=== 3) Enrichment ===")
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
    print("chipotle_enriched:")
    print(json.dumps(chipotle_enriched, indent=2, default=str) if chipotle_enriched else "None")
    print("\nfaasos_enriched:")
    print(json.dumps(faasos_enriched, indent=2, default=str) if faasos_enriched else "None")

    print("\n=== 4) Trace ===")
    from place_trace_debug import build_place_trace
    if chipotle_enriched:
        print("chipotle_trace:", json.dumps(build_place_trace(chipotle_enriched), indent=2, default=str))
    else:
        print("chipotle_trace: (no enriched payload)")
    if faasos_enriched:
        print("faasos_trace:", json.dumps(build_place_trace(faasos_enriched), indent=2, default=str))
    else:
        print("faasos_trace: (no enriched payload)")


if __name__ == "__main__":
    main()
