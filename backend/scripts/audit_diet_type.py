#!/usr/bin/env python3
"""
Classify every item by primary diet_type: "vegan" | "vegetarian" | "non_veg".

Heuristic priority:
1. If item name contains meat/fish/seafood keywords → non_veg.
2. Else if contains vegan-exclusive keywords (falafel, hummus, tofu, vegan) → vegan.
3. Else if contains dairy/egg keywords (paneer, cheese, egg, butter, ghee, milk,
   curd) OR rice/dal combos → vegetarian.
4. Else if item name has "veg " or "(veg)" or "vegetable" → vegetarian.
5. Default → non_veg (conservative for health tracking).

Also refines vegetarian_possible + vegan_possible flags to match diet_type.

Run: cd backend && python scripts/audit_diet_type.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEEDS_DIR = BACKEND / "data" / "chains"
INGESTED_PATH = BACKEND / "data" / "chain_menu_ingested.json"
COVERAGE_PATH = BACKEND / "data" / "chain_menu_coverage.json"

# Non-veg keywords (word-boundary matched). Any match = non_veg.
NON_VEG_WORDS = {
    # meats
    "chicken", "beef", "pork", "lamb", "mutton", "goat", "turkey", "duck", "bison",
    "veal", "buffalo", "sausage", "bacon", "ham", "pepperoni", "salami", "prosciutto",
    "chorizo", "pancetta", "meatball", "meatballs", "meat", "kebab", "seekh", "burra",
    "kofta", "keema", "tandoori", "biryani",  # biryani usually non-veg unless prefixed
    # seafood
    "fish", "salmon", "tuna", "prawn", "prawns", "shrimp", "crab", "lobster", "squid",
    "octopus", "clam", "mussel", "oyster", "anchovy", "sardine", "mackerel", "pomfret",
    "bhetki", "hilsa", "rohu", "cod", "tilapia", "sashimi", "nigiri",  # sushi usually has fish
    # specific dishes
    "bucket", "wings", "nugget", "nuggets", "drumstick", "thigh", "breast",
    "rogan", "rogan josh", "korma", "vindaloo",  # these are usually meat dishes
    "galouti", "boti", "mangsho", "jhinga", "chingri",
    "seafood", "crustacean", "shellfish",
    "chashu", "char siu", "char-siu",
}

# Words that look non-veg but in context can be veg — require explicit check
NON_VEG_FALSE_POSITIVES = {
    # "veg biryani" → veg; "paneer biryani" → veg; etc.
    # handled by veg prefix detection below
}

# Vegan-exclusive keywords. Only applies if no non-veg word matched.
VEGAN_WORDS = {
    "vegan", "falafel", "hummus", "tofu", "tempeh", "seitan", "edamame",
    "chickpea", "dal rice", "dal chawal", "dal + rice",
    "fruit bowl", "salad bowl (veg",  # weak
    "sourdough", "rice noodle", "rice noodles",
    "plant-based", "plant based", "jackfruit",
}

# Vegetarian (may contain dairy/egg) keywords. Applies if no non-veg match.
VEGETARIAN_WORDS = {
    "veggie", "vegie",  # "veggie burger" etc
    "paneer", "cheese", "egg", "omelette", "omelet", "butter", "ghee", "milk",
    "curd", "yogurt", "dahi", "lassi", "kheer", "rasmalai", "gulab jamun",
    "kulfi", "raita", "pakora", "samosa", "kachori", "bhature", "bhatura",
    "vada", "idli", "dosa", "uttapam", "upma", "pongal", "sambar",  # south indian veg
    "dal ", "dal,", "dal-", "dal)", "dal tadka", "dal makhani", "dal fry",
    "chole", "chhole", "rajma", "bhindi", "aloo", "gobi", "palak", "saag",
    "mushroom",  # ambiguous but usually veg
    "masala", "tikka masala",  # can be either; require other tokens
    "thali (veg", "thali(veg", "veg thali", "vegetarian", "veg ", " veg)", " (veg)",
    "dosa", "vada", "idli",  # duplicate for emphasis
    "bisibele", "curd rice", "khichdi", "poha", "upma",
    "croissant", "bagel", "toast", "pancake", "waffle", "scone", "muffin", "cake",
    "chocolate", "brownie", "cupcake", "donut", "doughnut", "pretzel",
}

_NON_VEG_RES = [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in NON_VEG_WORDS]
_VEGAN_RES = [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in VEGAN_WORDS]
_VEG_RES = [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in VEGETARIAN_WORDS]

_VEG_PREFIX_RE = re.compile(r"\b(veg|vegetarian|paneer|mushroom|tofu)\s+(biryani|tikka|kebab|pulao|fried rice|manchurian|65)\b", re.I)


def classify(item_name: str, existing_veg: bool = None, existing_vgn: bool = None, category: str = "") -> str:
    """Return 'non_veg' | 'vegetarian' | 'vegan'."""
    name = (item_name or "").lower()
    cat = (category or "").lower()
    # Handle explicit veg prefix that suppresses a meat-adjacent word
    if _VEG_PREFIX_RE.search(name):
        # "veg biryani" or "paneer biryani" etc. — these are veg, not non-veg
        # Check if actually contains a meat word beyond the prefix
        non_veg_hits = [rx for rx in _NON_VEG_RES if rx.search(name)]
        # If only biryani/tikka/kebab matched (common veg-prefix words), treat as veg
        overridable = {"biryani", "tikka", "kebab", "manchurian", "65", "rogan",
                       "rogan josh", "korma", "vindaloo", "galouti", "pulao", "pilaf"}
        meat_hits = []
        for rx in non_veg_hits:
            pat = rx.pattern.strip(r"\b")
            word = pat.replace(r"\ ", " ").replace("\\'", "'")
            # extract raw word from pattern; easier to just check against the overridable set
            raw = rx.pattern.replace(r"\b", "").replace("\\", "")
            if raw in overridable:
                continue
            meat_hits.append(raw)
        if not meat_hits:
            # Could still be vegan (tofu prefix). Check vegan words separately.
            if any(rx.search(name) for rx in _VEGAN_RES):
                return "vegan"
            return "vegetarian"

    # Check non-veg words
    for rx in _NON_VEG_RES:
        if rx.search(name):
            return "non_veg"

    # Check vegan words
    for rx in _VEGAN_RES:
        if rx.search(name):
            # if also has dairy, it's vegetarian
            if any(d in name for d in ("paneer", "cheese", "egg", "butter", "ghee", "milk", "curd", "yogurt")):
                return "vegetarian"
            return "vegan"

    # Check vegetarian words
    for rx in _VEG_RES:
        if rx.search(name):
            return "vegetarian"

    # Check existing flags as fallback
    if existing_vgn is True:
        return "vegan"
    if existing_veg is True:
        return "vegetarian"

    # Category-based default for beverage/dessert/side/snack/breakfast:
    # these rarely contain meat, so default to vegetarian.
    if cat in {"beverage", "dessert", "side", "snack", "breakfast"}:
        # Black coffee / tea / juice with no milk are vegan
        if any(tok in name for tok in ("black", "unsweetened", "pour-over", "cold brew", "espresso", "americano")):
            if not any(d in name for d in ("latte", "cappuccino", "flat white", "mocha")):
                return "vegan"
        return "vegetarian"

    # Default: non_veg (for category="entree" where meat is typical)
    return "non_veg"


def tag_item(item: dict, force: bool = True) -> bool:
    """Mutates item. Returns True if any field changed."""
    changed = False
    existing_veg = item.get("vegetarian_possible")
    existing_vgn = item.get("vegan_possible")
    diet = classify(item.get("item_name", ""), existing_veg, existing_vgn, item.get("category", ""))
    if item.get("diet_type") != diet:
        item["diet_type"] = diet
        changed = True
    # Align boolean flags with diet_type (source of truth now)
    new_veg = diet in ("vegetarian", "vegan")
    new_vgn = diet == "vegan"
    if item.get("vegetarian_possible") != new_veg:
        item["vegetarian_possible"] = new_veg
        changed = True
    if item.get("vegan_possible") != new_vgn:
        item["vegan_possible"] = new_vgn
        changed = True
    return changed


def run_on_seeds(dry_run: bool):
    files = sorted(SEEDS_DIR.glob("*.json"))
    items_changed = 0
    files_changed = 0
    for f in files:
        data = json.loads(f.read_text())
        file_changed = False
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            if tag_item(item):
                items_changed += 1
                file_changed = True
        if file_changed:
            files_changed += 1
            if not dry_run:
                with f.open("w", encoding="utf-8") as out:
                    json.dump(data, out, indent=2, ensure_ascii=False)
    return files_changed, items_changed, len(files)


def run_on_ingested(dry_run: bool):
    data = json.loads(INGESTED_PATH.read_text())
    chains = data.get("chains") or {}
    items_changed = 0
    for key, items in chains.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if tag_item(item):
                items_changed += 1
    if items_changed and not dry_run:
        with INGESTED_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return items_changed


def run_on_coverage(dry_run: bool):
    data = json.loads(COVERAGE_PATH.read_text())
    items_changed = 0
    for entry in data.get("chains") or []:
        for item in entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            if tag_item(item):
                items_changed += 1
    if items_changed and not dry_run:
        with COVERAGE_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return items_changed


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"=== diet_type audit ({'DRY-RUN' if dry_run else 'WRITE'}) ===\n")

    print("seeds (data/chains/*.json):")
    f, i, total = run_on_seeds(dry_run)
    print(f"  {f}/{total} files updated, {i} items tagged\n")

    print("ingested (chain_menu_ingested.json):")
    i = run_on_ingested(dry_run)
    print(f"  {i} items tagged\n")

    print("coverage (chain_menu_coverage.json):")
    i = run_on_coverage(dry_run)
    print(f"  {i} items tagged\n")

    # Distribution
    if not dry_run:
        from collections import Counter
        ingested = json.loads(INGESTED_PATH.read_text())
        dist = Counter()
        for items in (ingested.get("chains") or {}).values():
            for item in items:
                dist[item.get("diet_type", "unknown")] += 1
        total = sum(dist.values())
        print(f"=== diet_type distribution ({total} items) ===")
        for dt, n in sorted(dist.items(), key=lambda x: -x[1]):
            pct = 100 * n / total if total else 0
            bar = "█" * int(pct / 2)
            print(f"  {dt:<12} {n:>5} ({pct:5.1f}%)  {bar}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
