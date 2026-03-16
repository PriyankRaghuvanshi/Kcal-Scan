#!/usr/bin/env python3
"""
Chain menu status: list Wave 1 chains and item counts from Supabase.
Run from backend (with Supabase env): python3 scripts/chain_menu_status.py
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

WAVE1_CHAINS = [
    ("chipotle", "US"),
    ("taco_bell", "US"),
    ("panera", "US"),
    ("faasos", "IN"),
    ("wow_momo", "IN"),
    ("haldirams", "IN"),
    ("barbeque_nation", "IN"),
]


def main() -> None:
    from supabase_intelligence_store import get_chain_menu_items, list_chain_menu_chain_keys
    keys = list_chain_menu_chain_keys()
    print("chain_keys in profiles:", keys)
    print()
    print("Wave 1 readiness (chain_key, market_tag, item_count):")
    for chain_key, market_tag in WAVE1_CHAINS:
        items = get_chain_menu_items(chain_key, market_tag)
        n = len(items) if items else 0
        status = "ok" if n > 0 else "MISSING"
        print(f"  {chain_key} / {market_tag}: {n} items  [{status}]")
    print()
    total = sum(len(get_chain_menu_items(k, m)) or 0 for k, m in WAVE1_CHAINS)
    print(f"Total Wave 1 items: {total}")


if __name__ == "__main__":
    main()
