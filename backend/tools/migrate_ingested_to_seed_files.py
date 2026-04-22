"""One-shot migrator: copy real_menu items from data/chain_menu_ingested.json
to the corresponding data/chains/{chain_key}_{market_lower}.json seed files.

Why: Supabase sync (scripts/sync_chain_files_to_supabase.py) reads from
data/chains/*.json — NOT from the ingested store. So ingested real_menu
items never reach Supabase / the mobile /places/healthy recommendations
unless we backport them to the seed files here first.

Preserves brand_name + store_name_variants from the existing seed file
when present (those are hand-curated). Replaces items wholesale with the
real_menu payload.

Usage:
    python3 tools/migrate_ingested_to_seed_files.py --dry-run
    python3 tools/migrate_ingested_to_seed_files.py          # writes
    python3 tools/migrate_ingested_to_seed_files.py --chain starbucks --market IN
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

REPO = Path(__file__).resolve().parents[1]
INGESTED = REPO / "data" / "chain_menu_ingested.json"
SEED_DIR = REPO / "data" / "chains"


def load_existing_seed(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        with path.open() as fh:
            return json.load(fh)
    except Exception:
        return None


def derive_brand_name(items: List[Dict[str, Any]], chain_key: str) -> str:
    # Prefer existing seed brand_name; else title-case the chain_key
    return str(chain_key).replace("_", " ").title()


PRESERVE_FIELDS = ("image_url", "contains_palm_oil")


def merge_preserved_fields(
    ingested_items: List[Dict[str, Any]],
    existing: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """For each ingested item, copy over PRESERVE_FIELDS from the matching
    (by item_name) existing seed item when the existing value is set.
    Ingested data wins for all other fields (it's grounded + newer)."""
    if not existing or not isinstance(existing.get("items"), list):
        return ingested_items
    existing_by_name = {
        str(it.get("item_name") or "").strip().lower(): it
        for it in existing["items"]
        if isinstance(it, dict) and it.get("item_name")
    }
    merged: List[Dict[str, Any]] = []
    for it in ingested_items:
        out = dict(it)
        name_key = str(it.get("item_name") or "").strip().lower()
        match = existing_by_name.get(name_key)
        if match:
            for f in PRESERVE_FIELDS:
                val = match.get(f)
                if val not in (None, "", []):
                    out[f] = val
        merged.append(out)
    return merged


def build_seed_payload(
    chain_key: str,
    market_lower: str,
    items: List[Dict[str, Any]],
    existing: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    # Preserve manually-curated fields from existing seed when present
    brand_name = ""
    store_name_variants: List[str] = []
    if existing:
        brand_name = str(existing.get("brand_name") or "").strip()
        svs = existing.get("store_name_variants") or []
        if isinstance(svs, list):
            store_name_variants = [str(v) for v in svs if v]
    if not brand_name:
        brand_name = derive_brand_name(items, chain_key)

    first = items[0] if items else {}
    source_url = str(first.get("source_url") or "").strip()
    if not source_url and existing:
        source_url = str(existing.get("source_url") or "").strip()

    merged_items = merge_preserved_fields(items, existing)

    return {
        "brand_name": brand_name,
        "source_type": "official_website_menu",
        "source_url": source_url,
        "store_name_variants": store_name_variants,
        "items": merged_items,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--chain", help="only this chain_key")
    ap.add_argument("--market", help="only this market (uppercase)")
    args = ap.parse_args()

    with INGESTED.open() as fh:
        store = json.load(fh)

    chains = store.get("chains") or {}
    updated = 0
    created = 0
    skipped = 0
    for ck_m, items in chains.items():
        if not isinstance(items, list) or not items:
            continue
        first = items[0]
        if first.get("menu_item_source") != "real_menu":
            continue
        if "::" not in ck_m:
            continue
        ck, mk = ck_m.split("::", 1)
        if args.chain and args.chain.lower() != ck.lower():
            continue
        if args.market and args.market.upper() != mk.upper():
            continue
        seed_path = SEED_DIR / f"{ck.lower()}_{mk.lower()}.json"
        existing = load_existing_seed(seed_path)
        payload = build_seed_payload(ck, mk.lower(), items, existing)

        # Skip if seed file already identical (by item count AND first item_name)
        if existing and isinstance(existing.get("items"), list):
            e_items = existing["items"]
            if (
                len(e_items) == len(items)
                and (e_items[0].get("item_name") == items[0].get("item_name"))
                and (e_items[0].get("estimated_calories") == items[0].get("estimated_calories"))
            ):
                skipped += 1
                continue

        if args.dry_run:
            print(f"  [dry] {'UPDATE' if existing else 'CREATE'} {seed_path.name} ({len(items)} items)")
        else:
            seed_path.parent.mkdir(parents=True, exist_ok=True)
            with seed_path.open("w") as fh:
                json.dump(payload, fh, indent=2, ensure_ascii=False)
        if existing:
            updated += 1
        else:
            created += 1

    print(f"\n{'DRY RUN' if args.dry_run else 'DONE'}: updated={updated}, created={created}, skipped(no-change)={skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
