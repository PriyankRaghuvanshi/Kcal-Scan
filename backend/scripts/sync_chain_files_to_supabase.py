#!/usr/bin/env python3
"""
Sync every data/chains/{chain_key}_{market}.json seed file into Supabase
via chain_menu_supabase_sync.sync_chain_menu_to_supabase.

Unlike bulk_seed_all_chains.py (which ships hardcoded item data), this reads
whatever is currently on disk — so it picks up hand-authored edits, pilot
expansions, and LLM-curated items.

Usage (local, with prod Supabase creds in env):

    cd backend
    # dry-run: list what would be synced, no writes
    python scripts/sync_chain_files_to_supabase.py --dry-run

    # full sync
    python scripts/sync_chain_files_to_supabase.py

    # only specific chains (space-separated chain_keys)
    python scripts/sync_chain_files_to_supabase.py --chains mcdonalds chipotle britannia_cafe

    # only specific markets (default: all found in filenames)
    python scripts/sync_chain_files_to_supabase.py --markets us in

Required env vars: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY.
"""
import argparse
import os
import re
import sys
import time
from pathlib import Path

# Ensure backend is on path when invoked from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chain_menu_supabase_sync import sync_chain_menu_to_supabase  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"
FNAME_RE = re.compile(r"^(?P<chain_key>[a-z0-9_]+)_(?P<market>[a-z]{2,3})\.json$")


def discover_chain_files(markets_filter=None, chains_filter=None):
    files = []
    for path in sorted(DATA_DIR.glob("*.json")):
        m = FNAME_RE.match(path.name)
        if not m:
            continue
        chain_key = m.group("chain_key")
        market = m.group("market").upper()
        if markets_filter and market not in markets_filter:
            continue
        if chains_filter and chain_key not in chains_filter:
            continue
        files.append((chain_key, market, path))
    return files


def main():
    ap = argparse.ArgumentParser(description="Sync chain seed files to Supabase.")
    ap.add_argument("--dry-run", action="store_true", help="List targets without syncing.")
    ap.add_argument("--chains", nargs="*", help="Only these chain_keys.")
    ap.add_argument("--markets", nargs="*", help="Only these markets (e.g. US IN AU).")
    ap.add_argument("--limit", type=int, default=0, help="Stop after N chains (0 = no limit).")
    args = ap.parse_args()

    if not args.dry_run:
        if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
            print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set to run a real sync.")
            print("       Re-run with --dry-run to preview without writing.")
            sys.exit(2)

    markets_filter = {m.upper() for m in args.markets} if args.markets else None
    chains_filter = set(args.chains) if args.chains else None

    targets = discover_chain_files(markets_filter, chains_filter)
    if args.limit and len(targets) > args.limit:
        targets = targets[: args.limit]

    print(f"Targets: {len(targets)} chain-files under {DATA_DIR}")
    if markets_filter:
        print(f"  markets filter: {sorted(markets_filter)}")
    if chains_filter:
        print(f"  chains filter:  {sorted(chains_filter)}")
    print()

    if args.dry_run:
        for ck, mk, path in targets:
            print(f"  [dry] would sync {ck:<28} market={mk:<3} <- {path.name}")
        print(f"\n{len(targets)} chain-files would be synced (dry-run, no writes).")
        return

    started = time.time()
    ok_count = 0
    err_count = 0
    total_items = 0
    errors = []

    print(f"{'Chain':<28} {'Market':<4} {'Items':<6} Status")
    print("-" * 70)
    for ck, mk, path in targets:
        try:
            result = sync_chain_menu_to_supabase(ck, mk)
            if result.get("ok"):
                n = int(result.get("item_count") or 0)
                total_items += n
                ok_count += 1
                print(f"{ck:<28} {mk:<4} {n:<6} ok")
            else:
                err_count += 1
                err = result.get("error") or "?"
                errors.append((ck, mk, err))
                print(f"{ck:<28} {mk:<4} {'-':<6} FAIL: {err}")
        except Exception as e:
            err_count += 1
            errors.append((ck, mk, f"exc:{e}"))
            print(f"{ck:<28} {mk:<4} {'-':<6} EXC: {str(e)[:60]}")

    elapsed = time.time() - started
    print("-" * 70)
    print(f"Synced: {ok_count} ok, {err_count} failed, {total_items} items total in {elapsed:.1f}s")
    if errors:
        print("\nFailures:")
        for ck, mk, err in errors:
            print(f"  {ck} ({mk}): {err}")


if __name__ == "__main__":
    main()
