#!/usr/bin/env python3
"""
Normalize every data/chains/*.json seed file so the downstream Supabase sync +
mobile render has the required fields for trust labels, palm-oil badge, and
thumbnails. Idempotent: running twice yields the same output.

For each item, this tool:

  1. Ensures `menu_item_source` exists. If missing, defaults to "llm_curated"
     (never "official_published" — only the few curated chains we audited
     by hand keep that tag).
  2. Ensures `negative_flags` is an array.
  3. Ensures `contains_palm_oil` is a bool. If missing, infers from item_name
     keywords (see PALM_OIL_LIKELY / PALM_OIL_UNLIKELY). When inference is
     ambiguous, defaults to False (safer: no false positives on the 🌴 badge).
  4. Syncs `contains_palm_oil=True` into `negative_flags` so the mobile badge
     logic has a single consistent signal.
  5. Clears suspicious generic images (Indian_thali.jpg on a Spanish brand,
     Eggs_benedict.jpg on veggie pizza, etc.) to empty string so the UI
     falls back to the cuisine-aware tiered picker instead of showing a
     confidently-wrong thumbnail.

Run (dry-run first, always):

    cd backend
    python scripts/normalize_chain_seed_quality.py --dry-run
    python scripts/normalize_chain_seed_quality.py           # writes changes

After writing, re-run scripts/sync_chain_files_to_supabase.py to push the
fixed seeds into Supabase chain_menu_items.
"""
import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"

# Same fragments the auditor flags.
SUSPICIOUS_IMAGE_FRAGMENTS = [
    "Indian_thali.jpg",
    "Eggs_benedict.jpg",
    "Spaghetti_aglio_e_olio.jpg",
    "Tandoori_chicken_001.jpg",
]

# Lower-cased substrings that strongly imply the item contains palm oil.
PALM_OIL_LIKELY = [
    "pizza", "fries", "french fry", "french fries", "deep fry", "deep fried",
    "fried chicken", "nugget", "hash brown", "croissant", "donut", "doughnut",
    "biscuit", "cookie", "wafer", "cracker", "pastry", "puff",
    "ice cream", "chocolate bar", "chocolate spread", "nutella",
    "instant noodle", "cup noodle", "margarine", "butter spread",
    "samosa", "pakora", "bhatura", "poori", "puri", "papdi",
    "burger bun", "slider bun", "hot dog bun",
]

# Items where palm oil is *very unlikely* — whole foods, fresh prep.
PALM_OIL_UNLIKELY = [
    "grilled chicken", "grilled fish", "grilled paneer", "salad",
    "smoothie", "juice", "coffee", "latte", "cappuccino", "tea",
    "milk", "yogurt", "curd", "dahi",
    "boiled egg", "omelette", "poached egg", "scrambled egg",
    "rice bowl", "steamed", "tandoori", "roasted",
    "protein shake", "whey", "oats", "porridge",
    "fresh fruit", "fruit bowl", "raw vegetables",
]


def infer_palm_oil(item_name: str) -> bool | None:
    n = item_name.lower()
    if not n:
        return None
    for kw in PALM_OIL_LIKELY:
        if kw in n:
            return True
    for kw in PALM_OIL_UNLIKELY:
        if kw in n:
            return False
    return None


def normalize_item(item: dict) -> tuple[dict, list[str]]:
    """Return (possibly-mutated item, list of change tags). Idempotent."""
    changes: list[str] = []
    if not isinstance(item, dict):
        return item, changes

    name = str(item.get("item_name", "")).strip()

    # 1. menu_item_source
    if not str(item.get("menu_item_source") or "").strip():
        item["menu_item_source"] = "llm_curated"
        changes.append("menu_item_source")

    # 2. negative_flags
    nf = item.get("negative_flags")
    if not isinstance(nf, list):
        item["negative_flags"] = []
        changes.append("negative_flags")
        nf = item["negative_flags"]

    # 3. contains_palm_oil
    if "contains_palm_oil" not in item or not isinstance(item.get("contains_palm_oil"), bool):
        guess = infer_palm_oil(name)
        item["contains_palm_oil"] = bool(guess) if guess is not None else False
        changes.append("contains_palm_oil")

    # 4. Sync palm oil flag into negative_flags.
    flags = [str(x).strip() for x in (item.get("negative_flags") or [])]
    if item.get("contains_palm_oil") is True and "contains_palm_oil" not in flags:
        item["negative_flags"].append("contains_palm_oil")
        changes.append("negative_flags+=palm")
    if item.get("contains_palm_oil") is False and "contains_palm_oil" in flags:
        item["negative_flags"] = [x for x in item["negative_flags"] if str(x).strip() != "contains_palm_oil"]
        changes.append("negative_flags-=palm")

    # 5. Suspicious generic image -> clear.
    img = str(item.get("image_url") or "").strip()
    for frag in SUSPICIOUS_IMAGE_FRAGMENTS:
        if frag in img:
            frag_stem = frag.split(".")[0].replace("_", " ").lower()
            first_token = frag_stem.split()[0]
            if first_token not in name.lower():
                item["image_url"] = ""
                changes.append("image_url_cleared")
            break

    return item, changes


def normalize_file(path: Path, dry_run: bool) -> dict:
    stats = {"items_changed": 0, "changes": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        stats["error"] = str(e)
        return stats
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if not items:
        return stats
    any_changed = False
    for idx, it in enumerate(items):
        new_it, changes = normalize_item(dict(it) if isinstance(it, dict) else it)
        if changes:
            items[idx] = new_it
            any_changed = True
            stats["items_changed"] += 1
            for c in changes:
                stats["changes"][c] = stats["changes"].get(c, 0) + 1
    if any_changed and not dry_run:
        data["items"] = items
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return stats


def main():
    ap = argparse.ArgumentParser(description="Normalize chain seed JSON quality.")
    ap.add_argument("--dry-run", action="store_true", help="report only, don't write")
    ap.add_argument("--chains", nargs="*", help="filter by chain_key prefix")
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.json"))
    if args.chains:
        wanted = set(args.chains)
        files = [
            f for f in files
            if any(f.name.startswith(prefix + "_") or f.stem == prefix for prefix in wanted)
        ]

    total_files = len(files)
    files_touched = 0
    totals: dict = {}
    for path in files:
        stats = normalize_file(path, args.dry_run)
        if stats.get("items_changed", 0) > 0:
            files_touched += 1
        for k, v in stats.get("changes", {}).items():
            totals[k] = totals.get(k, 0) + v

    print(f"{'DRY-RUN' if args.dry_run else 'APPLIED'}: scanned {total_files}, changed {files_touched} files")
    for k, v in sorted(totals.items(), key=lambda kv: -kv[1]):
        print(f"  {v:6d}  {k}")
    if args.dry_run:
        print("\nRe-run without --dry-run to persist, then run sync_chain_files_to_supabase.py.")


if __name__ == "__main__":
    main()
