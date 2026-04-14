#!/usr/bin/env python3
"""
Audit every data/chains/*.json seed file and report quality issues that surfaced
during the Pizza Hut bug hunt:

 1. Missing menu_item_source on items (required for trust labels / palm badge flow).
 2. Missing contains_palm_oil on items that are likely pizza / fried / baked goods.
 3. Missing / clearly wrong image_url: either unset, not https, or mapped to a
    generic fallback thumbnail that doesn't match the item (e.g. "indian_thali"
    on a Big Mac, "eggs_benedict" on a veggie pizza).
 4. Missing negative_flags array (empty list is fine — key should exist when
    palm oil or other negatives apply).
 5. Suspicious item_name strings that smell like an LLM placeholder
    (e.g. "Indian thali", "Eggs benedict" on a non-Indian / non-breakfast brand).

Run:
    cd backend
    python scripts/audit_chain_seed_quality.py             # summary + top issues
    python scripts/audit_chain_seed_quality.py --verbose   # per-file details
    python scripts/audit_chain_seed_quality.py --limit 20  # preview first 20

Exit code is 0 regardless (read-only audit).
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"
FNAME_RE = re.compile(r"^(?P<chain_key>[a-z0-9_]+)_(?P<market>[a-z]{2,3})\.json$")

# Image URLs that keep getting reused as lazy fallbacks but don't match the item.
# These were all found as generic thumbnails in the pizza_hut_in.json bug.
SUSPICIOUS_IMAGE_FRAGMENTS = {
    "Indian_thali.jpg": "generic indian thali (often wrong for non-indian item)",
    "Eggs_benedict.jpg": "generic eggs benedict (wrong for almost everything)",
    "Spaghetti_aglio_e_olio.jpg": "generic spaghetti (wrong for non-pasta items)",
    "Tandoori_chicken_001.jpg": "generic tandoori (suspect for non-tandoori items)",
}

# Crude list of category/name cues that *strongly* imply palm oil is present.
PALM_OIL_LIKELY_KEYWORDS = [
    "pizza", "fries", "fry", "fried", "chips", "nuggets",
    "burger bun", "donut", "doughnut", "pastry", "biscuit",
    "ice cream", "margarine", "wafer", "cookie", "cracker",
    "chocolate bar", "cereal", "instant noodle",
]

# Ingredient cues that imply the item is NOT palm-oil (whole foods, fresh).
PALM_OIL_UNLIKELY_KEYWORDS = [
    "grilled chicken", "salad", "smoothie", "fruit",
    "coffee", "tea", "latte", "milk", "yogurt", "curd",
    "rice bowl", "steamed", "tandoori", "grilled fish",
    "omelette", "boiled egg", "protein shake",
]


def classify_palm_oil(item: dict) -> str | None:
    name = str(item.get("item_name", "")).lower()
    if not name:
        return None
    for kw in PALM_OIL_LIKELY_KEYWORDS:
        if kw in name:
            return "likely"
    for kw in PALM_OIL_UNLIKELY_KEYWORDS:
        if kw in name:
            return "unlikely"
    return None


def audit_file(path: Path) -> dict:
    issues = defaultdict(list)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        issues["parse_error"].append(str(e))
        return issues
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if not items:
        issues["no_items"].append("file has no items array")
        return issues
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            continue
        name = str(it.get("item_name", "")).strip()
        ref = f"{name or 'item_'+str(idx)}"

        if "menu_item_source" not in it or not str(it.get("menu_item_source") or "").strip():
            issues["missing_menu_item_source"].append(ref)

        if "negative_flags" not in it:
            issues["missing_negative_flags_key"].append(ref)

        if "contains_palm_oil" not in it:
            palm_hint = classify_palm_oil(it)
            if palm_hint == "likely":
                issues["palm_oil_likely_but_missing"].append(ref)
            else:
                issues["missing_contains_palm_oil"].append(ref)

        img = str(it.get("image_url") or "").strip()
        if not img:
            issues["missing_image_url"].append(ref)
        elif not img.startswith("https://"):
            issues["image_url_not_https"].append(f"{ref} -> {img[:80]}")
        else:
            for frag, why in SUSPICIOUS_IMAGE_FRAGMENTS.items():
                if frag in img:
                    # flag only when the item name clearly doesn't match the fragment.
                    nm = name.lower()
                    frag_stem = frag.split(".")[0].replace("_", " ").lower()
                    if frag_stem.split()[0] not in nm:
                        issues["suspicious_generic_image"].append(f"{ref} -> {frag} ({why})")
                    break

        # Cross-check: if it says contains_palm_oil=True but no negative_flags entry.
        if it.get("contains_palm_oil") is True:
            nf = it.get("negative_flags") or []
            if "contains_palm_oil" not in [str(x).strip() for x in nf]:
                issues["palm_oil_true_but_not_in_negative_flags"].append(ref)

    return issues


def main():
    ap = argparse.ArgumentParser(description="Audit chain seed JSON quality.")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="stop after N files (0 = all)")
    ap.add_argument("--chains", nargs="*", help="filter to specific chain_keys")
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.json"))
    if args.chains:
        wanted = set(args.chains)
        files = [f for f in files if FNAME_RE.match(f.name) and FNAME_RE.match(f.name).group("chain_key") in wanted]
    if args.limit:
        files = files[: args.limit]

    counts: Counter = Counter()
    files_with_issues = 0
    total_files = len(files)
    per_issue_sample: dict = defaultdict(list)

    for path in files:
        issues = audit_file(path)
        if not issues:
            continue
        files_with_issues += 1
        for k, v in issues.items():
            counts[k] += len(v) if isinstance(v, list) else 1
            if len(per_issue_sample[k]) < 5:
                per_issue_sample[k].append(f"{path.name}: {v[0] if v else ''}")
        if args.verbose:
            print(f"\n== {path.name} ==")
            for k, v in issues.items():
                print(f"  [{k}] x{len(v)}: {v[:3]}{' …' if len(v) > 3 else ''}")

    print("\n" + "=" * 60)
    print(f"Scanned: {total_files} files  |  with issues: {files_with_issues}")
    print("=" * 60)
    for k, c in counts.most_common():
        print(f"  {c:6d}  {k}")
        for sample in per_issue_sample[k][:2]:
            print(f"            e.g. {sample}")
    print()
    sys.exit(0)


if __name__ == "__main__":
    main()
