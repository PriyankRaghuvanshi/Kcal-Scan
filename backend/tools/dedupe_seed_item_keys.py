"""Fix duplicate item_keys in data/chains/*.json seed files by appending a
slugified serving_size suffix when multiple items share the same item_key.

Cause: Gemini ingestion derives item_key by slugging item_name only, so
size variants (e.g., Cold Brew Tall/Grande/Venti) collide. Postgres upsert
then fails with `21000: ON CONFLICT DO UPDATE command cannot affect row a
second time`.

Usage:
    python3 tools/dedupe_seed_item_keys.py           # writes in place
    python3 tools/dedupe_seed_item_keys.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEED_DIR = REPO / "data" / "chains"


def slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", str(s or "").strip().lower())
    return s.strip("_")


def dedupe_file(path: Path, dry: bool) -> tuple[int, int]:
    """Returns (items_adjusted, duplicate_groups_resolved)."""
    with path.open() as fh:
        seed = json.load(fh)
    items = seed.get("items")
    if not isinstance(items, list) or not items:
        return 0, 0

    key_counts = Counter(i.get("item_key", "") for i in items if isinstance(i, dict))
    dup_keys = {k for k, n in key_counts.items() if n > 1 and k}
    if not dup_keys:
        return 0, 0

    adjusted = 0
    for it in items:
        if not isinstance(it, dict):
            continue
        key = it.get("item_key", "")
        if key not in dup_keys:
            continue
        serving = slug(it.get("serving_size", ""))
        if not serving:
            # fallback: use calories + carbs to distinguish
            serving = f"c{int(it.get('estimated_calories') or 0)}p{int(it.get('estimated_protein_g') or 0)}"
        new_key = f"{key}__{serving}"
        it["item_key"] = new_key
        adjusted += 1

    # If suffixing didn't fully disambiguate (e.g., same serving size twice),
    # append a numeric suffix.
    final_counts = Counter(i.get("item_key", "") for i in items if isinstance(i, dict))
    still_dup = {k for k, n in final_counts.items() if n > 1 and k}
    if still_dup:
        seen: dict[str, int] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            key = it.get("item_key", "")
            if key in still_dup:
                n = seen.get(key, 0) + 1
                seen[key] = n
                if n > 1:
                    it["item_key"] = f"{key}_{n}"
                    adjusted += 1

    if not dry:
        with path.open("w") as fh:
            json.dump(seed, fh, indent=2, ensure_ascii=False)
    return adjusted, len(dup_keys)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files_changed = 0
    total_adjusted = 0
    problem_chains = []
    for p in sorted(SEED_DIR.glob("*.json")):
        adj, groups = dedupe_file(p, args.dry_run)
        if adj:
            files_changed += 1
            total_adjusted += adj
            problem_chains.append((p.name, adj, groups))

    for name, adj, groups in problem_chains:
        print(f"  {name}: {adj} items re-keyed across {groups} dup groups")
    print(f"\n{'DRY RUN' if args.dry_run else 'DONE'}: {files_changed} files, {total_adjusted} items re-keyed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
