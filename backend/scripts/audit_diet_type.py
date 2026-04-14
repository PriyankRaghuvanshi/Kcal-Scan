#!/usr/bin/env python3
"""
Audit + fix diet_type tags across data/chains/*.json.

Problem: llm_curated seeds frequently have wrong diet_type — e.g. Amul
Shrikhand tagged "non_veg" when it's a dairy dessert. Because the sync
code treats diet_type as authoritative for vegetarian_possible/vegan_possible,
a wrong tag here mis-classifies the item in the mobile app.

Strategy (conservative — never defaults to non_veg on ambiguous items):
  1. If name contains a strong meat/fish keyword -> non_veg (meat dominates).
  2. Else if name contains an "egg" token -> non_veg in IN market, vegetarian
     elsewhere (India treats eggs as non-veg by default).
  3. Else if name contains a vegan keyword AND no dairy keyword -> vegan.
  4. Else if name contains a strong veg keyword -> vegetarian.
  5. Else: leave unchanged (ambiguous).

Only touches items whose menu_item_source is NOT in TRUSTED_SOURCES
(official_published, name_verified_pdf_estimated_nutrition, official_nutrition).
When flipping diet_type, also sets vegetarian_possible/vegan_possible to stay
consistent with chain_menu_supabase_sync._apply_diet_type.

Usage:
  cd backend
  python3 scripts/audit_diet_type.py            # dry-run report
  python3 scripts/audit_diet_type.py --write    # apply changes
  python3 scripts/audit_diet_type.py --chains amul_parlour   # subset
"""
import argparse
import json
import re
from pathlib import Path
from collections import Counter, defaultdict

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"

TRUSTED_SOURCES = {
    "official_published",
    "name_verified_pdf_estimated_nutrition",
    "official_nutrition",
}

# Strong non-veg keywords. If any fires, the item is non_veg even if a veg
# token also appears ("paneer chicken roll" -> non_veg because of chicken).
# Exception: VEG_OVERRIDE_RE wins over these (see below).
NON_VEG_KEYWORDS = [
    # poultry
    r"\bchicken\b", r"\bmurg(h?)\b", r"\bmurgh\b", r"\bduck\b", r"\bturkey\b",
    r"\bgoose\b", r"\bquail\b",
    # red meat
    r"\bmutton\b", r"\blamb\b", r"\bgoat\b", r"\bgosht\b", r"\bkeema\b",
    r"\bseekh\b", r"\bnihari\b", r"\brogan\s*josh\b", r"\bgalouti\b",
    r"\bshami\b", r"\bbeef\b", r"\bsteak\b", r"\bbrisket\b", r"\bveal\b",
    r"\bcarne\b", r"\bcarnitas\b", r"\bbarbacoa\b", r"\bboti\b",
    r"\bmangsho\b", r"\bjhinga\b", r"\bchingri\b",
    # pork
    r"\bpork\b", r"\bham\b", r"\bbacon\b", r"\bsausage\b", r"\bsalami\b",
    r"\bpepperoni\b", r"\bprosciutto\b", r"\bchorizo\b", r"\bpancetta\b",
    r"\banchovy\b", r"\banchovies\b",
    # fish / seafood
    r"\bfish\b", r"\btuna\b", r"\bsalmon\b", r"\bcod\b", r"\btrout\b",
    r"\btilapia\b", r"\bmackerel\b", r"\bsardine\b", r"\bbhekti\b",
    r"\bhilsa\b", r"\brohu\b", r"\bkatla\b", r"\bpomfret\b",
    r"\bprawn\b", r"\bshrimp\b", r"\bcrab\b", r"\blobster\b", r"\bmussel\b",
    r"\bclam\b", r"\boyster\b", r"\bsquid\b", r"\boctopus\b", r"\bcalamari\b",
    r"\bsashimi\b", r"\bnigiri\b", r"\bmaki\b(?!\s*roll\s*(?:veg))",
    # general
    r"\bmeat\b", r"\bmeatball\b", r"\bcold\s*cuts?\b", r"\bseafood\b",
    r"\bshellfish\b", r"\bchashu\b", r"\bchar[-\s]?siu\b",
]
NON_VEG_RE = re.compile("|".join(NON_VEG_KEYWORDS), re.I)

# Veg overrides that win over non-veg matches. E.g. "malai kofta" contains
# "kofta" but is always veg. Apply these BEFORE the non-veg check.
VEG_OVERRIDE_KEYWORDS = [
    r"\bmalai\s+kofta\b",
    r"\bveg\s+kofta\b",
    r"\bpaneer\s+kofta\b",
    r"\bveg\s+biryani\b",
    r"\bveg\s+pulao\b",
    r"\bpaneer\s+biryani\b",
    r"\bsubz(i|e)\s+biryani\b",
]
VEG_OVERRIDE_RE = re.compile("|".join(VEG_OVERRIDE_KEYWORDS), re.I)

# Egg detection — handled separately for market-aware rule.
EGG_RE = re.compile(r"\b(eggs?|omelettes?|omelet|frittata|scrambled)\b", re.I)

# Strong vegetarian keywords.
VEGETARIAN_KEYWORDS = [
    # Indian veg mains
    r"\bpaneer\b", r"\btofu\b", r"\bdal\b", r"\bdaal\b", r"\btoor\b",
    r"\bmasoor\b", r"\bmoong\b", r"\burad\b",
    r"\bchana\b", r"\bchole\b", r"\brajma\b", r"\bsambhar\b", r"\bsambar\b",
    r"\bkadhi\b", r"\bpakora\b", r"\bbhajji\b",
    r"\bpav\s*bhaji\b", r"\bpoha\b", r"\bupma\b", r"\bvada\s*pav\b",
    r"\bmisal\b", r"\bbhature\b", r"\bmissi\s*roti\b", r"\bchaap\b",
    r"\bidli\b", r"\bdosa\b", r"\buttapam\b", r"\bkachori\b",
    r"\bnavratan\b", r"\bmix\s*veg\b", r"\bveg\s*kolhapuri\b",
    r"\bkhichdi\b", r"\bcurd\s*rice\b", r"\bbisibele\b", r"\bsaag\b",
    # Indian veg vegetables
    r"\baloo\b", r"\bpalak\b", r"\bspinach\b", r"\bbhindi\b", r"\bokra\b",
    r"\bbaingan\b", r"\bbrinjal\b", r"\beggplant\b", r"\bcauliflower\b",
    r"\bgobi\b", r"\bzucchini\b", r"\basparagus\b", r"\bpotato\b",
    r"\bmushroom\b",
    # Indian dairy desserts
    r"\bshrikhand\b", r"\blassi\b", r"\bkulfi\b", r"\brasmalai\b",
    r"\brasgulla\b", r"\bgulab\s*jamun\b", r"\bjalebi\b", r"\bhalwa\b",
    r"\bkheer\b", r"\bghevar\b", r"\bbarfi\b", r"\bladdu\b",
    r"\bpedha\b", r"\brabri\b", r"\bphirni\b", r"\bpayasam\b",
    r"\bmishti\s*doi\b", r"\bdoi\b", r"\braita\b",
    # Ice cream / global dairy desserts
    r"\bice\s*cream\b", r"\bicecream\b", r"\bchocobar\b", r"\bgelato\b",
    r"\bsundae\b", r"\bmilkshake\b", r"\bfrozen\s*yogurt\b",
    r"\bfrozen\s*dessert\b", r"\bsoft\s*serve\b", r"\bvanilla\s*cup\b",
    r"\bbutterscotch\s*cone\b", r"\bchoco\s*cone\b",
    # Dairy
    r"\byogurt\b", r"\byoghurt\b", r"\bcurd\b", r"\bdahi\b",
    r"\bcheese\b", r"\bghee\b",
    # Italian that's clearly veg
    r"\bmargherita\b", r"\bveg\s+pizza\b", r"\bpaneer\s+pizza\b",
    r"\bmushroom\s+pizza\b", r"\bcheese\s+pizza\b", r"\bveggie\s+pizza\b",
    r"\bpasta\s+marinara\b", r"\baglio\s*e\s*olio\b",
    # Middle Eastern veg
    r"\bfalafel\b", r"\bhummus\b", r"\bbaba\s*ganoush\b", r"\bmutabbal\b",
    r"\btabbouleh\b",
    # Explicit veg qualifiers
    r"\(veg\)", r"\bveggie\b", r"\bvegetarian\b",
    r"\bveg\b",  # standalone word "veg"
]
VEGETARIAN_RE = re.compile("|".join(VEGETARIAN_KEYWORDS), re.I)

# Vegan-specific. Only apply vegan if NO dairy keyword is also present.
VEGAN_KEYWORDS = [
    r"\bvegan\b", r"\bplant[-\s]based\b",
    r"\bsoy\s*milk\b", r"\balmond\s*milk\b", r"\boat\s*milk\b",
    r"\bcoconut\s*milk\b",
]
VEGAN_RE = re.compile("|".join(VEGAN_KEYWORDS), re.I)

# Dairy keywords — presence means not vegan.
DAIRY_KEYWORDS = [
    r"\bpaneer\b", r"\bghee\b", r"\bmalai\b", r"\bcheese\b",
    r"\bbutter\b(?!\s*chicken)",  # "butter chicken" should not trigger this
    r"\bcream\b", r"\bmilk\b(?!\s*(?:almond|soy|oat|coconut))",
    r"\bcurd\b", r"\bdahi\b", r"\byogurt\b", r"\byoghurt\b",
    r"\bshrikhand\b", r"\blassi\b", r"\bkulfi\b", r"\bice\s*cream\b",
    r"\bicecream\b", r"\bkheer\b", r"\brasmalai\b", r"\brabri\b",
    r"\bmishti\s*doi\b",
]
DAIRY_RE = re.compile("|".join(DAIRY_KEYWORDS), re.I)


def classify(name: str, market: str) -> str:
    """Return 'non_veg' / 'vegetarian' / 'vegan' / '' (ambiguous)."""
    n = str(name or "")
    if not n.strip():
        return ""
    # Veg override wins (e.g. "malai kofta", "veg biryani").
    if VEG_OVERRIDE_RE.search(n):
        return "vegetarian"
    # Strong non-veg.
    if NON_VEG_RE.search(n):
        return "non_veg"
    # Egg: market-aware.
    if EGG_RE.search(n):
        return "non_veg" if str(market or "").upper() == "IN" else "vegetarian"
    # Vegan: keyword present + no dairy.
    if VEGAN_RE.search(n) and not DAIRY_RE.search(n):
        return "vegan"
    # Strong vegetarian keyword.
    if VEGETARIAN_RE.search(n):
        return "vegetarian"
    return ""  # ambiguous


DIET_TYPE_TO_BOOLS = {
    "vegan": {"vegan_possible": True, "vegetarian_possible": True},
    "vegetarian": {"vegan_possible": False, "vegetarian_possible": True},
    "non_veg": {"vegan_possible": False, "vegetarian_possible": False},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="Persist changes. Default: dry-run.")
    ap.add_argument("--chains", nargs="*", help="Limit to these chain_keys.")
    args = ap.parse_args()

    flips = defaultdict(list)
    counts = Counter()
    files_touched = 0
    chains_filter = set(args.chains) if args.chains else None

    for path in sorted(DATA_DIR.glob("*.json")):
        stem = path.stem
        try:
            chain_key, market = stem.rsplit("_", 1)
        except ValueError:
            continue
        if chains_filter and chain_key not in chains_filter:
            continue
        market = market.upper()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        file_changed = False
        for it in items:
            if not isinstance(it, dict):
                continue
            src = str(it.get("menu_item_source") or "").strip()
            if src in TRUSTED_SOURCES:
                counts["skipped_trusted"] += 1
                continue
            name = str(it.get("item_name") or "").strip()
            if not name:
                continue
            current = str(it.get("diet_type") or "").strip().lower()
            predicted = classify(name, market)
            if not predicted:
                counts["ambiguous_left_alone"] += 1
                continue
            if predicted == current:
                counts["already_correct"] += 1
                continue
            direction = f"{current or '(missing)'}->{predicted}"
            flips[direction].append((stem, name, current or "(missing)", predicted))
            counts[direction] += 1
            if args.write:
                it["diet_type"] = predicted
                bools = DIET_TYPE_TO_BOOLS.get(predicted)
                if bools:
                    for k, v in bools.items():
                        it[k] = v
                file_changed = True
        if file_changed and args.write:
            files_touched += 1
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    mode = "APPLIED" if args.write else "DRY-RUN"
    print(f"\n=== {mode} ===")
    for direction, rows in sorted(flips.items()):
        print(f"\n{direction} ({len(rows)} items):")
        for stem, name, old, new in rows[:25]:
            print(f"  {stem:<30} {name!r}")
        if len(rows) > 25:
            print(f"  ... and {len(rows) - 25} more")
    print("\n--- Summary ---")
    for k, v in sorted(counts.items()):
        print(f"  {k:<30} {v}")
    if args.write:
        print(f"\nWrote {files_touched} files. Run sync_chain_files_to_supabase.py next.")
    else:
        print("\nRe-run with --write to persist, then resync.")


if __name__ == "__main__":
    main()
