#!/usr/bin/env python3
"""
Audit + enrich diet tags across all seed files.

Adds two new boolean fields to every item:
  halal_possible      — False if item name suggests pork/bacon/alcohol
  gluten_free_possible — False if item name suggests wheat-containing carb base

Preserves existing fields. Only fills in missing ones by default.
Use --force to overwrite existing tags.

Run:  cd backend && python scripts/audit_diet_tags.py [--dry-run] [--force]
"""
import json
import re
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEEDS_DIR = BACKEND / "data" / "chains"
INGESTED_PATH = BACKEND / "data" / "chain_menu_ingested.json"
COVERAGE_PATH = BACKEND / "data" / "chain_menu_coverage.json"

# Keyword heuristics (all lowercased, applied to item_name)

# Pork / alcohol / haram-incompatible ingredients. Conservative — default True,
# only flag False for clearly pork- or alcohol-containing items.
# Uses regex word boundaries to avoid false positives (e.g., "ham" in "hamburger").
HALAL_DISQUALIFIERS_WORDS = {
    # pork products
    "pork", "bacon", "ham", "pepperoni", "salami", "prosciutto", "chorizo",
    "pancetta", "guanciale", "lardo", "gammon", "carnitas",
    # alcoholic cooking
    "wine", "rum", "brandy", "whiskey", "whisky",
}
# Multi-word pork items (not word-bounded since they're phrases).
HALAL_DISQUALIFIERS_PHRASES = {
    "bbq pork", "pulled pork", "char siu", "char-siu",
}
# Words that LOOK like haram but aren't (substring false positives).
HALAL_SAFEWORD_PHRASES = {
    "hamburger", "cheeseburger", "turkey ham", "vegan ham", "chicken ham",
    "mutton ham", "pork-free",
}

# Gluten-containing bases. Items with these in name are NOT gluten-free.
GLUTEN_SOURCES = {
    # breads
    "bread", "baguette", "ciabatta", "pita", "bagel", "roll", "bun", "focaccia",
    "naan", "roti", "paratha", "chapati", "kulcha", "poori", "bhature", "tortilla",
    # pasta
    "pasta", "spaghetti", "fettuccine", "linguine", "penne", "rigatoni", "lasagna",
    "lasagne", "ravioli", "tortellini", "gnocchi", "macaroni", "udon", "ramen",
    "noodle", "noodles", "lo mein", "chow mein", "pad thai", "pad-thai",
    # pizzas
    "pizza", "flatbread", "calzone",
    # wraps / sandwiches
    "sandwich", "wrap", "burrito", "quesadilla", "kathi", "roll ", "taco",
    # baked goods
    "croissant", "muffin", "donut", "doughnut", "bagel", "waffle", "pancake",
    "pastry", "pastries", "biscuit", "biscotti", "shrewsbury", "pretzel",
    # asian dumplings / breads
    "dumpling", "dumplings", "dim sum", "dimsum", "momo", "wonton", "siu mai",
    "gyoza", "baozi", "bao", "bun", "har gau", "jiaozi",
    # indian
    "samosa", "kachori", "bhatura", "vada pav", "misal pav", "pav", "frankie",
    "seekh naan", "tandoori roti",
    # burgers/chickens (though patties can be GF, bun isn't)
    "burger", "slider",
    # cakes / sweets with wheat
    "cake", "brownie", "cookie", "scone", "dosa", "idli",  # idli is rice-based but sambar + dal is fine; dosa can be wheat? most are rice+urad (GF). Keep conservative: include.
    # Actually idli/dosa are GF. Remove them from list.
    # Remove "idli" and "dosa" from GLUTEN_SOURCES — they're rice-based.
}
# Remove the falsely-flagged ones (idli/dosa are GF)
GLUTEN_SOURCES.discard("idli")
GLUTEN_SOURCES.discard("dosa")

# "Hamburger" / "Cheeseburger" is wheat bun. "Burger" already in list. OK.

# Categories that are reliably GF: sides like "side" "salad" "sashimi" "soup"
# don't override; rely on name-level rules.


_HALAL_WORD_RES = [re.compile(r"\b" + re.escape(w) + r"\b", re.I) for w in HALAL_DISQUALIFIERS_WORDS]


def is_halal_safe(item_name: str) -> bool:
    name = (item_name or "").lower()
    # Remove safeword substrings first so they don't trigger disqualifiers.
    # ("hamburger" -> stripped so "ham" won't false-positive)
    stripped = name
    for sw in HALAL_SAFEWORD_PHRASES:
        stripped = stripped.replace(sw, "")
    # Phrase disqualifiers (multi-word).
    for phrase in HALAL_DISQUALIFIERS_PHRASES:
        if phrase in stripped:
            return False
    # Word-boundary disqualifiers (single words).
    for rx in _HALAL_WORD_RES:
        if rx.search(stripped):
            return False
    return True


def is_gluten_free(item_name: str, category: str = "") -> bool:
    name = (item_name or "").lower()
    cat = (category or "").lower()
    for token in GLUTEN_SOURCES:
        if token in name:
            return False
    # category hints
    if cat in {"entree", "side", "beverage", "dessert"}:
        # stand-alone proteins, salads, most drinks, some desserts are GF
        return True
    return True


def tag_item(item: dict, force: bool = False) -> bool:
    """Mutates item in place. Returns True if any field was added/changed."""
    changed = False
    name = item.get("item_name", "")
    cat = item.get("category", "")
    if force or "halal_possible" not in item:
        new_val = is_halal_safe(name)
        if item.get("halal_possible") != new_val:
            item["halal_possible"] = new_val
            changed = True
    if force or "gluten_free_possible" not in item:
        new_val = is_gluten_free(name, cat)
        if item.get("gluten_free_possible") != new_val:
            item["gluten_free_possible"] = new_val
            changed = True
    return changed


def run_on_seeds(force: bool, dry_run: bool):
    files = sorted(SEEDS_DIR.glob("*.json"))
    tagged = 0
    items_changed = 0
    for f in files:
        data = json.loads(f.read_text())
        file_changed = False
        for item in data.get("items") or []:
            if not isinstance(item, dict):
                continue
            if tag_item(item, force):
                items_changed += 1
                file_changed = True
        if file_changed:
            tagged += 1
            if not dry_run:
                with f.open("w", encoding="utf-8") as out:
                    json.dump(data, out, indent=2, ensure_ascii=False)
    return tagged, items_changed, len(files)


def run_on_ingested(force: bool, dry_run: bool):
    data = json.loads(INGESTED_PATH.read_text())
    chains = data.get("chains") or {}
    entries_changed = 0
    items_changed = 0
    for key, items in chains.items():
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if tag_item(item, force):
                items_changed += 1
                entries_changed = entries_changed if items_changed else entries_changed
    if items_changed and not dry_run:
        with INGESTED_PATH.open("w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
    return items_changed, len(chains)


def run_on_coverage(force: bool, dry_run: bool):
    data = json.loads(COVERAGE_PATH.read_text())
    items_changed = 0
    for entry in data.get("chains") or []:
        for item in entry.get("items") or []:
            if not isinstance(item, dict):
                continue
            if tag_item(item, force):
                items_changed += 1
    if items_changed and not dry_run:
        with COVERAGE_PATH.open("w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
    return items_changed


def main():
    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    print(f"mode: {'DRY-RUN' if dry_run else 'WRITE'} {'(force overwrite)' if force else '(fill-missing only)'}")
    print(f"\n=== seeds (data/chains/*.json) ===")
    seed_files, seed_items, total = run_on_seeds(force, dry_run)
    print(f"  total seed files: {total}")
    print(f"  files with new tags: {seed_files}")
    print(f"  items tagged: {seed_items}")

    print(f"\n=== ingested (chain_menu_ingested.json) ===")
    ing_items, ing_entries = run_on_ingested(force, dry_run)
    print(f"  chain entries: {ing_entries}")
    print(f"  items tagged: {ing_items}")

    print(f"\n=== coverage (chain_menu_coverage.json) ===")
    cov_items = run_on_coverage(force, dry_run)
    print(f"  items tagged: {cov_items}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
