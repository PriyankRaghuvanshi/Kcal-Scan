"""Audit all chain menu items for data-quality bugs.

Scans data/chain_menu_ingested.json and applies rule-based validators
to surface diet contradictions, allergen mistags, macro implausibility,
and source-label gaps. Outputs a severity-ranked JSON report and a
console summary.

Run:
    python3 tools/audit_chain_menus.py
    python3 tools/audit_chain_menus.py --chain subway::AU
    python3 tools/audit_chain_menus.py --severity critical,high
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from typing import Any, Dict, List, Tuple

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INGESTED_PATH = os.path.join(REPO_ROOT, "data", "chain_menu_ingested.json")
REPORT_PATH = os.path.join(REPO_ROOT, "data", "menu_audit_report.json")

NON_VEG_TOKENS = (
    "chicken", "beef", "steak", "pork", "bacon", "lamb", "mutton",
    "turkey", "fish", "salmon", "tuna", "shrimp", "prawn", "crab", "lobster",
    "anchovy", "sardine", "mince", "sausage", "pepperoni", "salami", "keema",
    "tandoori chicken", "butter chicken", "carnitas", "barbacoa", "chorizo",
    "pastrami", "wing", "drumstick", "nugget", "patty melt", "murgh",
    "mutton ", "ham sandwich", "ham,", "ham roll", "deli ham",
)
PORK_TOKENS = (
    "pork", "bacon", "pepperoni", "salami", "chorizo", "carnitas",
    "pastrami", "bbq rib", "back rib", "spare rib", "pulled pork",
    "ham sandwich", "ham roll", "deli ham",
)
AMBIGUOUS_VEG_NONVEG = ("tikka", "kebab", "kabab", "kofta", "shami", "tandoori")
DAIRY_TOKENS = (
    "cheese", "paneer", "butter", "ghee", "cream", "yogurt", "yoghurt",
    "milk", "lassi", "kulfi", "kheer", "rabri", "ranch", "alfredo",
    "mozzarella", "cheddar", "parmesan", "feta", "ricotta",
)
EGG_TOKENS = (" egg ", " eggs ", " egg,", "omelet", "omelette", "frittata", "quiche", "scrambled")
NUT_TOKENS = ("peanut", "cashew", "almond", "walnut", "pecan", "pistachio", "hazelnut", "macadamia", " nut ", " nuts ", " satay ")
SHELLFISH_TOKENS = ("shrimp", "prawn", "crab", "lobster", "scallop", "clam", "mussel", "oyster", "calamari", "squid")
GLUTEN_TOKENS = (
    "bread", "bun", "sub ", "sub,", "wrap", "roll", "pizza", "burger",
    "pasta", "noodle", "spaghetti", "lasagna", "ramen", "udon", "soba",
    "naan", "roti", "paratha", "kulcha", "puri", "samosa", "kachori",
    "momo", "dumpling", "dosa", "uttapam", "sandwich", "panini",
    "biscuit", "cookie", "cake", "muffin", "donut", "doughnut", "pancake",
    "waffle", "tortilla", "taco", "quesadilla", "burrito", "calzone",
)
GENERIC_BANNED = (
    "greek yogurt protein bowl", "grilled protein bowl",
    "protein bowl", "protein plate", "lean wrap", "healthy plate",
)


def _name_has(name: str, tokens: Tuple[str, ...]) -> bool:
    n = f" {name.lower()} "
    return any(t in n for t in tokens)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def audit_item(chain_market: str, item: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Return list of flag dicts for this item. Empty if clean."""
    flags: List[Dict[str, Any]] = []
    name = str(item.get("item_name") or "").strip()
    name_lc = name.lower()
    diet = str(item.get("diet_type") or "").strip().lower()
    src = str(item.get("menu_item_source") or "").strip().lower()
    conf = _safe_float(item.get("confidence"), 0.0)
    kcal = _safe_float(item.get("estimated_calories"), 0.0)
    p = _safe_float(item.get("estimated_protein_g"), 0.0)
    f = _safe_float(item.get("estimated_fat_g"), 0.0)
    c = _safe_float(item.get("estimated_carbs_g"), 0.0)

    def add(severity: str, code: str, detail: str) -> None:
        flags.append({
            "chain_market": chain_market,
            "item_key": item.get("item_key"),
            "item_name": name,
            "severity": severity,
            "code": code,
            "detail": detail,
        })

    # --- Diet contradictions (CRITICAL — wrong info to user) ---
    if diet in ("vegetarian", "vegan") and _name_has(name_lc, NON_VEG_TOKENS):
        add("critical", "diet_contradicts_name",
            f"diet_type={diet!r} but name contains meat token")
    if item.get("vegetarian_possible") is True and _name_has(name_lc, NON_VEG_TOKENS):
        add("critical", "vegetarian_possible_meat",
            "vegetarian_possible=true but name contains meat token")
    if item.get("vegan_possible") is True:
        if _name_has(name_lc, NON_VEG_TOKENS):
            add("critical", "vegan_possible_meat",
                "vegan_possible=true but name contains meat token")
        elif _name_has(name_lc, DAIRY_TOKENS):
            add("critical", "vegan_possible_dairy",
                "vegan_possible=true but name contains dairy")
        elif _name_has(name_lc, EGG_TOKENS):
            add("critical", "vegan_possible_egg",
                "vegan_possible=true but name contains egg")
    if item.get("halal_possible") is True and _name_has(name_lc, PORK_TOKENS):
        add("critical", "halal_possible_pork",
            "halal_possible=true but name contains pork/bacon/ham")

    # --- Allergen flag inconsistencies (HIGH — filter routes wrongly) ---
    if item.get("contains_gluten") is False and _name_has(name_lc, GLUTEN_TOKENS):
        add("high", "gluten_flag_wrong",
            "contains_gluten=false but name implies wheat/bread")
    if item.get("gluten_free_possible") is True and _name_has(name_lc, GLUTEN_TOKENS):
        add("high", "gluten_free_wrong",
            "gluten_free_possible=true but name implies wheat/bread")
    if item.get("contains_dairy") is False and _name_has(name_lc, DAIRY_TOKENS):
        add("high", "dairy_flag_wrong",
            "contains_dairy=false but name implies dairy")
    if item.get("contains_egg") is False and _name_has(name_lc, EGG_TOKENS):
        add("high", "egg_flag_wrong",
            "contains_egg=false but name implies egg")
    if item.get("contains_nuts") is False and _name_has(name_lc, NUT_TOKENS):
        add("high", "nuts_flag_wrong",
            "contains_nuts=false but name implies nuts")
    if item.get("contains_shellfish") is False and _name_has(name_lc, SHELLFISH_TOKENS):
        add("high", "shellfish_flag_wrong",
            "contains_shellfish=false but name implies shellfish")

    # --- Macro plausibility (MEDIUM — bad recs) ---
    is_drink = any(t in name_lc for t in ("coffee", "tea", "americano", "espresso", "cold brew", "pour-over", "water", "soda water"))
    if kcal < 5 or (kcal < 30 and not is_drink and "salad" not in name_lc):
        add("medium", "kcal_too_low", f"estimated_calories={kcal}")
    if kcal > 2500:
        add("medium", "kcal_too_high", f"estimated_calories={kcal}")
    for label, val in (("protein", p), ("fat", f), ("carbs", c)):
        if val < 0:
            add("medium", f"{label}_negative", f"value={val}")
    if p > 0 and kcal > 0 and (p * 4) > kcal * 1.05:
        add("medium", "protein_exceeds_kcal",
            f"protein={p}g implies {p*4}kcal but stated {kcal}")
    if f > 0 and kcal > 0 and (f * 9) > kcal * 1.05:
        add("medium", "fat_exceeds_kcal",
            f"fat={f}g implies {f*9}kcal but stated {kcal}")
    if kcal > 0 and (p + f + c) > 0:
        implied = (p * 4) + (c * 4) + (f * 9)
        drift = abs(implied - kcal) / kcal
        # kJ-as-kcal bug: if stated kcal is 3-5x the implied, it's likely a kJ value.
        if implied > 0 and kcal >= implied * 2.5:
            add("high", "kcal_likely_kj",
                f"stated {kcal:.0f} is {kcal/implied:.1f}x P+F+C implied ({implied:.0f}) — likely kJ value stored in kcal field (÷4.184={kcal/4.184:.0f})")
        elif drift > 0.30:
            add("high", "macro_kcal_mismatch",
                f"P+F+C implies {implied:.0f}kcal vs stated {kcal:.0f} (drift {drift*100:.0f}%)")
    if kcal > 0 and p == 0 and f == 0 and c == 0:
        add("high", "macros_all_zero", "kcal>0 but all macros=0 (extraction likely dropped macros)")

    # --- Source label gap (LOW — systemic, blocks strong-evidence path) ---
    if src != "real_menu":
        add("low", "source_not_real_menu",
            f"menu_item_source={src!r} (blocks has_strong_menu_evidence path)")

    # --- Naming hygiene ---
    if any(t in name_lc for t in GENERIC_BANNED):
        add("low", "generic_banned_name",
            f"name uses generic banned token (will be sanitized to fallback copy)")

    # --- Confidence vs specificity_tier ---
    tier = str(item.get("chosen_candidate_specificity_tier") or "").lower()
    if tier == "exact_menu_match" and conf < 0.7:
        add("low", "low_confidence_exact_match",
            f"specificity_tier=exact_menu_match but confidence={conf}")

    return flags


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain", help="Filter to a single chain_market key (e.g. subway::AU)")
    parser.add_argument("--severity", default="critical,high,medium,low",
                        help="Comma-separated severities to include")
    parser.add_argument("--limit", type=int, default=0,
                        help="Print at most N flags to console (0=all)")
    args = parser.parse_args()

    sev_filter = {s.strip().lower() for s in args.severity.split(",") if s.strip()}

    with open(INGESTED_PATH) as fh:
        store = json.load(fh)
    chains = store.get("chains", {})

    all_flags: List[Dict[str, Any]] = []
    items_by_chain: Dict[str, int] = {}
    flagged_items_by_chain: Dict[str, int] = collections.defaultdict(int)

    for chain_market, items in chains.items():
        if args.chain and chain_market != args.chain:
            continue
        if not isinstance(items, list):
            continue
        items_by_chain[chain_market] = len(items)
        for item in items:
            flags = audit_item(chain_market, item)
            flags = [fl for fl in flags if fl["severity"] in sev_filter]
            if flags:
                flagged_items_by_chain[chain_market] += 1
                all_flags.extend(flags)

    # Aggregate
    by_severity = collections.Counter(fl["severity"] for fl in all_flags)
    by_code = collections.Counter(fl["code"] for fl in all_flags)
    by_chain = collections.Counter(fl["chain_market"] for fl in all_flags)
    by_market = collections.Counter(fl["chain_market"].split("::")[-1] for fl in all_flags)

    total_items = sum(items_by_chain.values())
    total_flagged = sum(flagged_items_by_chain.values())

    report = {
        "summary": {
            "total_chains_scanned": len(items_by_chain),
            "total_items_scanned": total_items,
            "total_items_flagged": total_flagged,
            "total_flags": len(all_flags),
            "by_severity": dict(by_severity),
            "by_code": dict(by_code.most_common()),
            "by_market": dict(by_market.most_common()),
            "top_chains_by_flags": dict(by_chain.most_common(30)),
        },
        "flags": all_flags,
    }

    with open(REPORT_PATH, "w") as fh:
        json.dump(report, fh, indent=2)

    # Console summary
    print(f"\n=== MENU AUDIT REPORT ===")
    print(f"Chains scanned:    {len(items_by_chain)}")
    print(f"Items scanned:     {total_items}")
    print(f"Items flagged:     {total_flagged} ({total_flagged*100/max(total_items,1):.1f}%)")
    print(f"Total flags:       {len(all_flags)}")
    print(f"\nBy severity:")
    for sev in ("critical", "high", "medium", "low"):
        if sev in by_severity:
            print(f"  {sev:10s} {by_severity[sev]}")
    print(f"\nTop flag codes:")
    for code, n in by_code.most_common(15):
        print(f"  {n:6d}  {code}")
    print(f"\nTop chains by flag count:")
    for chain, n in by_chain.most_common(15):
        items = items_by_chain.get(chain, 0)
        print(f"  {n:6d}  {chain:30s} ({items} items)")
    print(f"\nReport written to: {REPORT_PATH}")

    if args.limit > 0:
        print(f"\n--- First {args.limit} flags ---")
        for fl in all_flags[:args.limit]:
            print(f"  [{fl['severity'].upper():8s}] {fl['chain_market']:20s} "
                  f"{fl['item_name'][:40]:40s} {fl['code']}: {fl['detail']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
