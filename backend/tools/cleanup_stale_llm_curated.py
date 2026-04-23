"""Surgical cleanup of stale llm_curated rows in Supabase chain_menu_items.

For each chain::market whose seed file now has real_menu items, find any
llm_curated Supabase rows whose normalized item_name collides with a
real_menu item_name and delete only those duplicates. Unique llm_curated
items (seasonal, regional, or things the LLM guessed correctly beyond the
official nutrition page) survive.

Usage:
    python3 tools/cleanup_stale_llm_curated.py --dry-run
    python3 tools/cleanup_stale_llm_curated.py           # writes

Requires SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY in env.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Set, Tuple

REPO = Path(__file__).resolve().parents[1]
SEED_DIR = REPO / "data" / "chains"

_norm_re = re.compile(r"[^a-z0-9]+")


def norm_name(s: str) -> str:
    return _norm_re.sub("", str(s or "").lower()).strip()


def curl_json(url: str, method: str = "GET", extra_headers: List[str] = None, timeout: int = 30):
    headers = [
        "-H", f"apikey: {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
        "-H", f"Authorization: Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
    ]
    if extra_headers:
        for h in extra_headers:
            headers += ["-H", h]
    cmd = ["curl", "-s", "-X", method, url, *headers]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    try:
        return json.loads(r.stdout) if r.stdout else None
    except Exception:
        return r.stdout


def load_real_pairs_with_names() -> Dict[Tuple[str, str], Set[str]]:
    """Returns {(chain_key, market_upper): {normalized_item_name, ...}} from seed files."""
    out: Dict[Tuple[str, str], Set[str]] = {}
    for p in SEED_DIR.glob("*.json"):
        try:
            seed = json.load(open(p))
        except Exception:
            continue
        items = seed.get("items")
        if not isinstance(items, list) or not items:
            continue
        if items[0].get("menu_item_source") != "real_menu":
            continue
        stem = p.stem
        idx = stem.rfind("_")
        if idx < 0:
            continue
        ck, mk = stem[:idx], stem[idx + 1 :].upper()
        names = {norm_name(i.get("item_name")) for i in items if isinstance(i, dict)}
        names.discard("")
        if names:
            out[(ck, mk)] = names
    return out


def fetch_llm_curated_rows(ck: str, mk: str) -> List[Dict]:
    url = (
        f"{os.environ['SUPABASE_URL']}/rest/v1/chain_menu_items"
        f"?chain_key=eq.{ck}&market_tag=eq.{mk}"
        f"&menu_item_source=eq.llm_curated"
        f"&select=item_key,item_name"
    )
    rows = curl_json(url)
    if not isinstance(rows, list):
        return []
    return rows


def delete_item_key(ck: str, mk: str, item_key: str) -> bool:
    url = (
        f"{os.environ['SUPABASE_URL']}/rest/v1/chain_menu_items"
        f"?chain_key=eq.{ck}&market_tag=eq.{mk}"
        f"&menu_item_source=eq.llm_curated"
        f"&item_key=eq.{item_key}"
    )
    result = subprocess.run([
        "curl", "-s", "-w", "%{http_code}", "-X", "DELETE", url,
        "-H", f"apikey: {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
        "-H", f"Authorization: Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
    ], capture_output=True, text=True, timeout=30)
    return result.stdout.strip().endswith(("200", "204"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_ROLE_KEY"):
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        return 1

    real = load_real_pairs_with_names()
    print(f"Chain::markets with real_menu seed items: {len(real)}")

    total_deletable = 0
    total_kept = 0
    plan: List[Tuple[str, str, str, str]] = []  # (ck, mk, item_key, item_name)

    for (ck, mk), real_names in sorted(real.items()):
        llm_rows = fetch_llm_curated_rows(ck, mk)
        if not llm_rows:
            continue
        for row in llm_rows:
            iname_norm = norm_name(row.get("item_name", ""))
            if iname_norm and iname_norm in real_names:
                plan.append((ck, mk, row.get("item_key", ""), row.get("item_name", "")))
                total_deletable += 1
            else:
                total_kept += 1

    print(f"Duplicate llm_curated rows (same item name as real_menu): {total_deletable}")
    print(f"Unique llm_curated rows (kept — no real_menu duplicate): {total_kept}")

    if args.dry_run:
        print("\nSample of plan (first 20):")
        for ck, mk, ik, iname in plan[:20]:
            print(f"  DELETE {ck}::{mk}  item_key={ik}  name={iname!r}")
        return 0

    deleted = 0
    failed = 0
    for ck, mk, ik, iname in plan:
        if not ik:
            continue
        ok = delete_item_key(ck, mk, ik)
        if ok:
            deleted += 1
        else:
            failed += 1
    print(f"\nDeleted: {deleted}   Failed: {failed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
