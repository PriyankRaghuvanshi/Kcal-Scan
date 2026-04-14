#!/usr/bin/env python3
"""
Delete chain_menu_items rows in Supabase whose item_key is no longer present
in the local seed file. Needed after item renames (which change item_key via
the slug) — the upsert adds the new key alongside the old one, leaving the
old row as stale data the mobile app might still surface.

Usage (from backend/):
  railway run python3 scripts/cleanup_stale_chain_items.py --dry-run
  railway run python3 scripts/cleanup_stale_chain_items.py --chains pizza_hut la_pinoz  # subset
  railway run python3 scripts/cleanup_stale_chain_items.py                              # all chains
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from chain_menu_supabase_sync import _slug_for_item_key  # noqa: E402
from supabase_intelligence_store import (  # noqa: E402
    _http_get_json,
    _requests_module,
    _supabase_base_url,
    _supabase_headers,
)


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"


def _ensure_env() -> None:
    if not (os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_SERVICE_ROLE_KEY")):
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set", file=sys.stderr)
        sys.exit(2)


def fetch_existing_keys(chain_key: str, market: str) -> list:
    url = f"{_supabase_base_url()}/chain_menu_items"
    params = {
        "chain_key": f"eq.{chain_key}",
        "market_tag": f"eq.{market}",
        "select": "item_key,item_name",
    }
    _, body = _http_get_json(url, headers=_supabase_headers(), params=params, timeout=20)
    return body or []


def delete_row(chain_key: str, market: str, item_key: str) -> int:
    url = f"{_supabase_base_url()}/chain_menu_items"
    params = {
        "chain_key": f"eq.{chain_key}",
        "market_tag": f"eq.{market}",
        "item_key": f"eq.{item_key}",
    }
    requests = _requests_module()
    if requests is not None:
        r = requests.delete(url, headers=_supabase_headers(), params=params, timeout=20)
        r.raise_for_status()
        return r.status_code
    # urllib fallback (may hit SSL issues on some python builds)
    import urllib.parse
    import urllib.request
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{url}?{qs}", headers=_supabase_headers(), method="DELETE")
    with urllib.request.urlopen(req, timeout=20) as r:  # nosec B310
        return r.status


def compute_seed_keys(seed_path: Path) -> set:
    try:
        data = json.load(seed_path.open())
    except Exception:
        return set()
    items = data.get("items") or []
    keys = set()
    seen: dict = {}
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        k = str(it.get("item_key") or "").strip()
        if not k:
            name = str(it.get("item_name") or it.get("name") or "").strip()
            base = _slug_for_item_key(name) if name else f"item_{i+1}"
            cnt = seen.get(base, 0) + 1
            seen[base] = cnt
            k = base if cnt == 1 else f"{base}_{cnt}"
        keys.add(k)
    return keys


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="List deletions without executing.")
    ap.add_argument("--chains", nargs="*", help="Only clean these chain_keys.")
    args = ap.parse_args()

    chains_filter = set(args.chains) if args.chains else None
    _ensure_env()

    total_stale = 0
    files_checked = 0
    for path in sorted(DATA_DIR.glob("*.json")):
        stem = path.stem
        try:
            chain_key, market = stem.rsplit("_", 1)
        except ValueError:
            continue
        market = market.upper()
        if chains_filter and chain_key not in chains_filter:
            continue
        seed_keys = compute_seed_keys(path)
        if not seed_keys:
            continue
        files_checked += 1
        try:
            remote = fetch_existing_keys(chain_key, market)
        except Exception as exc:
            print(f"  fetch failed for {chain_key} {market}: {exc}")
            continue
        stale = [r for r in remote if r.get("item_key") not in seed_keys]
        if not stale:
            continue
        for r in stale:
            total_stale += 1
            marker = "[dry]" if args.dry_run else "[del]"
            print(f"  {marker} {chain_key:<25} {market:<3} {r.get('item_key','?'):<50} ({r.get('item_name','?')})")
            if not args.dry_run:
                try:
                    delete_row(chain_key, market, r["item_key"])
                except Exception as exc:
                    print(f"    delete failed: {exc}")
    mode = "would delete" if args.dry_run else "deleted"
    print(f"\n{mode} {total_stale} stale rows across {files_checked} chain-files.")


if __name__ == "__main__":
    main()
