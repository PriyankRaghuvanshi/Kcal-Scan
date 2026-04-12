#!/usr/bin/env python3
"""
Merge data/chains/*.json seed files into the live runtime registries.

Writes to:
  - data/chain_menu_coverage.json  (alias/name matching, items)
  - data/chain_menu_ingested.json  (menu items served by get_chain_items_for_registry)

Preserves hand-curated entries: if (chain_key, country_code) already exists in
coverage.json or {chain_key}::{COUNTRY} exists in ingested.json, the seed is SKIPPED.
Only adds missing entries.

Usage:
    cd backend && python scripts/merge_chain_seeds_to_registry.py [--dry-run]
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
CHAINS_DIR = BACKEND / "data" / "chains"
COVERAGE_PATH = BACKEND / "data" / "chain_menu_coverage.json"
INGESTED_PATH = BACKEND / "data" / "chain_menu_ingested.json"

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(name: str) -> str:
    s = _SLUG_RE.sub("_", (name or "").lower()).strip("_")
    return s or "item"


def derive_satiety(protein_g: int, calories: int) -> str:
    if protein_g >= 25:
        return "high"
    if protein_g >= 15 or calories <= 400:
        return "medium"
    return "low"


def parse_filename(stem: str):
    chain_key, _, market = stem.rpartition("_")
    if not chain_key or len(market) != 2:
        return None, None
    return chain_key.lower(), market.upper()


def seed_to_coverage_entry(seed: dict, chain_key: str, country: str) -> dict:
    url = str(seed.get("source_url") or "").strip()
    items_out = []
    for raw in seed.get("items") or []:
        if not isinstance(raw, dict):
            continue
        cal = int(raw.get("estimated_calories") or 0)
        pro = int(raw.get("estimated_protein_g") or 0)
        items_out.append({
            "item_name": str(raw.get("item_name") or "").strip(),
            "category": str(raw.get("category") or "entree"),
            "estimated_calories": cal,
            "estimated_protein_g": pro,
            "estimated_carbs_g": int(raw.get("estimated_carbs_g") or 0),
            "estimated_fat_g": int(raw.get("estimated_fat_g") or 0),
            "estimated_satiety": derive_satiety(pro, cal),
            "menu_item_confidence": round(float(raw.get("confidence") or 0.82), 2),
        })
    return {
        "chain_id": f"{chain_key}_{country.lower()}",
        "chain_key": chain_key,
        "chain_name": str(seed.get("brand_name") or chain_key.replace("_", " ").title()),
        "country_code": country,
        "source_type": "official_website_menu",
        "official_menu_source_url": url,
        "menu_last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "chain_aliases": list(seed.get("store_name_variants") or []),
        "items": items_out,
    }


def seed_to_ingested_items(seed: dict, chain_key: str, country: str) -> list:
    url = str(seed.get("source_url") or "").strip()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for raw in seed.get("items") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("item_name") or "").strip()
        if not name:
            continue
        out.append({
            "chain_key": chain_key,
            "source_type": "official_website_menu",
            "source_url": url,
            "market_tag": country,
            "item_key": f"{chain_key}_{slug(name)}",
            "item_name": name,
            "category": str(raw.get("category") or "entree"),
            "estimated_calories": int(raw.get("estimated_calories") or 0),
            "estimated_protein_g": int(raw.get("estimated_protein_g") or 0),
            "estimated_fat_g": int(raw.get("estimated_fat_g") or 0),
            "estimated_carbs_g": int(raw.get("estimated_carbs_g") or 0),
            "serving_size": "",
            "confidence": round(float(raw.get("confidence") or 0.82), 2),
            "supports_swaps": True,
            "negative_flags": [],
            "last_ingested_at": ts,
            "active": True,
            "chosen_candidate_specificity_tier": "exact_menu_match",
            "menu_item_source": "ingested_chain_item",
        })
    return out


def main():
    dry_run = "--dry-run" in sys.argv

    seed_files = sorted(CHAINS_DIR.glob("*.json"))
    print(f"seed files: {len(seed_files)}")

    # Load existing stores
    with COVERAGE_PATH.open("r") as f:
        coverage = json.load(f)
    with INGESTED_PATH.open("r") as f:
        ingested = json.load(f)

    cov_chains = coverage.get("chains") or []
    ing_chains = ingested.get("chains") or {}

    existing_cov = {(c.get("chain_key"), c.get("country_code")) for c in cov_chains}
    existing_ing = set(ing_chains.keys())

    cov_before = len(cov_chains)
    ing_before = len(ing_chains)

    added_cov = 0
    added_ing = 0
    skipped_cov = 0
    skipped_ing = 0
    errors = []

    for path in seed_files:
        chain_key, country = parse_filename(path.stem)
        if not chain_key or not country:
            errors.append(f"bad filename: {path.stem}")
            continue

        try:
            seed = json.loads(path.read_text())
        except Exception as e:
            errors.append(f"parse error {path.stem}: {e}")
            continue

        # Coverage
        if (chain_key, country) in existing_cov:
            skipped_cov += 1
        else:
            entry = seed_to_coverage_entry(seed, chain_key, country)
            cov_chains.append(entry)
            existing_cov.add((chain_key, country))
            added_cov += 1

        # Ingested
        ing_key = f"{chain_key}::{country}"
        if ing_key in existing_ing:
            skipped_ing += 1
        else:
            items = seed_to_ingested_items(seed, chain_key, country)
            if items:
                ing_chains[ing_key] = items
                existing_ing.add(ing_key)
                added_ing += 1

    coverage["chains"] = cov_chains
    ingested["chains"] = ing_chains
    ingested["updated_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\n=== COVERAGE ({COVERAGE_PATH.name}) ===")
    print(f"  before: {cov_before}   after: {len(cov_chains)}   added: {added_cov}   skipped(existing): {skipped_cov}")
    print(f"\n=== INGESTED ({INGESTED_PATH.name}) ===")
    print(f"  before: {ing_before}   after: {len(ing_chains)}   added: {added_ing}   skipped(existing): {skipped_ing}")
    if errors:
        print(f"\nERRORS: {len(errors)}")
        for e in errors[:20]:
            print(f"  {e}")

    if dry_run:
        print("\n--dry-run: no files written")
        return 0

    with COVERAGE_PATH.open("w") as f:
        json.dump(coverage, f, indent=2, ensure_ascii=False)
    with INGESTED_PATH.open("w") as f:
        json.dump(ingested, f, indent=2, ensure_ascii=False)
    print("\nwrote coverage + ingested.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
