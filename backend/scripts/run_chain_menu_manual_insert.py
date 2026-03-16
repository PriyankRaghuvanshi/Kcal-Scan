#!/usr/bin/env python3
"""
Manual insert of one Chipotle US item into chain_menu_items (for debugging).
Load env first so Supabase vars are set, then run this script.

  cd backend
  set -a && source .env && set +a   # or: source ../.env
  echo $SUPABASE_URL
  echo $SUPABASE_SERVICE_ROLE_KEY | wc -c
  python3 scripts/run_chain_menu_manual_insert.py

Expected: SUPABASE DEBUG lines (URL, params, status, body) and return value 1.
If return 0: check POST status and body in the debug output; fix env or table/schema.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

# Optional: load .env if present (so you can run without sourcing first)
_env = BACKEND / ".env"
if not _env.exists():
    _env = BACKEND.parent / ".env"
if _env.exists():
    with _env.open() as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                k, v = k.strip(), v.strip().strip('"').strip("'")
                os.environ.setdefault(k, v)

from supabase_intelligence_store import upsert_chain_menu_items

ITEMS = [
    {
        "item_key": "chipotle_test_item",
        "item_name": "Chipotle Test Item",
        "category": "bowl",
        "estimated_calories": 500,
        "estimated_protein_g": 30,
        "estimated_carbs_g": 40,
        "estimated_fat_g": 18,
        "vegetarian_possible": False,
        "vegan_possible": False,
        "confidence": 0.8,
        "negative_flags": [],
        "menu_item_source": "seed_estimated",
        "source_url": "https://www.chipotle.com/nutrition-calculator",
        "protein_density_score": 6.0,
        "fat_loss_fit_score": 45.0,
    }
]

if __name__ == "__main__":
    result = upsert_chain_menu_items("chipotle", "US", ITEMS)
    print("Return value:", result)
    sys.exit(0 if result == 1 else 1)
