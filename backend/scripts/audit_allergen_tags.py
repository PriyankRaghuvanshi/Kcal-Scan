#!/usr/bin/env python3
"""
Add 7 allergen boolean tags to every item:
  contains_nuts, contains_dairy, contains_gluten, contains_soy,
  contains_shellfish, contains_egg, contains_sesame

Conservative defaults: flag True when keywords match the item name; False otherwise.
Users with severe allergies should still confirm with the venue — these are
heuristic labels for filtering, not safety guarantees.

Run: cd backend && python scripts/audit_allergen_tags.py [--dry-run]
"""
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEEDS_DIR = BACKEND / "data" / "chains"
INGESTED_PATH = BACKEND / "data" / "chain_menu_ingested.json"
COVERAGE_PATH = BACKEND / "data" / "chain_menu_coverage.json"

# === Allergen keyword sets (word-boundary regex match) ===

NUTS_WORDS = {
    "almond", "almonds", "cashew", "cashews", "walnut", "walnuts", "pecan", "pecans",
    "pistachio", "pistachios", "hazelnut", "hazelnuts", "macadamia", "brazil nut",
    "pine nut", "pine nuts", "peanut", "peanuts", "nut", "nuts", "nutella",
    "pesto",  # often contains pine nuts
    "kaju", "badam", "pista",  # Indian names for cashew/almond/pistachio
    "marzipan", "praline", "almond flour",
}
# pesto doesn't always have nuts but typically yes — conservative flag

DAIRY_WORDS = {
    "milk", "cheese", "butter", "cream", "yogurt", "yoghurt", "curd", "paneer",
    "ghee", "whey", "dahi", "lassi", "kheer", "rasmalai", "ricotta", "mozzarella",
    "parmesan", "cheddar", "feta", "brie", "goat cheese", "halloumi", "burrata",
    "ice cream", "gelato", "frozen yogurt", "custard", "pudding", "kulfi",
    "malai", "rabri", "shrikhand", "raita", "mawa", "khoa",
    "cappuccino", "latte", "flat white", "mocha", "macchiato", "chai latte",
    "butter chicken", "butter naan", "cheesecake", "cheeseburger",
}
DAIRY_SAFEWORDS = {
    "coconut milk", "almond milk", "oat milk", "soy milk", "cashew milk",
    "rice milk", "non-dairy", "nondairy", "dairy-free", "dairy free",
}

GLUTEN_WORDS = {
    "bread", "baguette", "ciabatta", "pita", "bagel", "bun", "focaccia",
    "naan", "roti", "paratha", "chapati", "kulcha", "poori", "bhatura", "bhature", "tortilla",
    "pasta", "spaghetti", "fettuccine", "linguine", "penne", "rigatoni", "lasagna",
    "lasagne", "ravioli", "tortellini", "gnocchi", "macaroni", "noodle", "noodles",
    "udon", "ramen", "lo mein", "chow mein", "pad thai", "pad-thai",
    "pizza", "flatbread", "calzone", "wrap", "sandwich", "burrito", "quesadilla",
    "kathi", "roll", "taco",
    "croissant", "muffin", "donut", "doughnut", "waffle", "pancake", "pretzel",
    "dumpling", "dim sum", "momo", "wonton", "siu mai", "gyoza", "baozi",
    "samosa", "kachori", "vada pav", "misal pav", "pav", "frankie",
    "burger", "slider",
    "cake", "brownie", "cookie", "scone",
    "biryani",  # usually has wheat garnish/bread but served with rice; conservative
    "seitan", "soy sauce",  # soy sauce contains wheat
}
GLUTEN_SAFEWORDS = {
    "gluten-free", "gluten free", "rice noodle", "rice noodles", "rice paper",
    "corn tortilla", "gluten-free bread",
}

SOY_WORDS = {
    "soy", "soya", "tofu", "edamame", "miso", "tempeh", "soybean", "soybeans",
    "soy sauce", "teriyaki",  # teriyaki sauce contains soy
    "tamari",
    # branded soy items
    "textured vegetable protein", "tvp",
}

SHELLFISH_WORDS = {
    "shrimp", "prawn", "prawns", "crab", "lobster", "squid", "calamari",
    "octopus", "clam", "clams", "mussel", "mussels", "oyster", "oysters",
    "scallop", "scallops", "crayfish", "crawfish",
    "chingri", "jhinga",  # Bengali/Hindi for prawn/shrimp
}

EGG_WORDS = {
    "egg", "eggs", "omelette", "omelet", "omlette",
    "mayo", "mayonnaise", "aioli", "hollandaise", "bearnaise", "carbonara",
    "custard", "meringue", "souffle", "quiche", "frittata",
    "bhurji", "anda", "akuri", "french toast",
    "egg white", "egg yolk", "cake", "brownie",  # baked goods usually have egg
}
EGG_SAFEWORDS = {
    "eggless", "vegan", "eggfree", "egg-free",
}

SESAME_WORDS = {
    "sesame", "tahini", "hummus", "halva", "halvah", "halawa",
    "til",  # Hindi for sesame
    "benne", "gingelly",
    "everything bagel",  # has sesame
    "zaatar", "za'atar",  # may contain sesame
}

# Compiled regex patterns
_RES = {
    "contains_nuts": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in NUTS_WORDS],
    "contains_dairy": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in DAIRY_WORDS],
    "contains_gluten": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in GLUTEN_WORDS],
    "contains_soy": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in SOY_WORDS],
    "contains_shellfish": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in SHELLFISH_WORDS],
    "contains_egg": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in EGG_WORDS],
    "contains_sesame": [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in SESAME_WORDS],
}
_SAFEWORD_PHRASES = {
    "contains_dairy": DAIRY_SAFEWORDS,
    "contains_gluten": GLUTEN_SAFEWORDS,
    "contains_egg": EGG_SAFEWORDS,
}


def check_allergen(name: str, allergen_field: str) -> bool:
    """Return True if item_name contains the given allergen. Safewords explicitly
    negate — if the item name contains e.g. 'gluten-free', return False regardless."""
    lower = (name or "").lower()
    for sw in _SAFEWORD_PHRASES.get(allergen_field, set()):
        if sw in lower:
            return False
    return any(rx.search(lower) for rx in _RES[allergen_field])


ALL_ALLERGENS = list(_RES.keys())


def tag_item(item: dict) -> bool:
    changed = False
    name = item.get("item_name", "")
    for field in ALL_ALLERGENS:
        new_val = check_allergen(name, field)
        if item.get(field) != new_val:
            item[field] = new_val
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
            if isinstance(item, dict) and tag_item(item):
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
    items_changed = 0
    for items in (data.get("chains") or {}).values():
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict) and tag_item(item):
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
            if isinstance(item, dict) and tag_item(item):
                items_changed += 1
    if items_changed and not dry_run:
        with COVERAGE_PATH.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    return items_changed


def main():
    dry_run = "--dry-run" in sys.argv
    print(f"=== allergen audit ({'DRY-RUN' if dry_run else 'WRITE'}) ===\n")

    print("seeds:")
    f, i, total = run_on_seeds(dry_run)
    print(f"  {f}/{total} files, {i} items tagged\n")

    print("ingested:")
    i = run_on_ingested(dry_run)
    print(f"  {i} items tagged\n")

    print("coverage:")
    i = run_on_coverage(dry_run)
    print(f"  {i} items tagged\n")

    # Distribution summary
    if not dry_run:
        from collections import Counter
        data = json.loads(INGESTED_PATH.read_text())
        counts = Counter()
        total_items = 0
        for items in (data.get("chains") or {}).values():
            for item in items:
                if not isinstance(item, dict):
                    continue
                total_items += 1
                for field in ALL_ALLERGENS:
                    if item.get(field):
                        counts[field] += 1
        print(f"=== allergen prevalence ({total_items} items) ===")
        for field in ALL_ALLERGENS:
            n = counts[field]
            pct = 100 * n / total_items if total_items else 0
            bar = "█" * int(pct / 2)
            print(f"  {field:<20} {n:>5} ({pct:5.1f}%)  {bar}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
