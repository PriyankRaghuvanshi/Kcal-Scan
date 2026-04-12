#!/usr/bin/env python3
"""
Audit + expand store_name_variants across all seed files.

For every chain, ensure aliases include common typo/accent/abbreviation variants
so Google Places name matching is robust.

Rules applied:
  - apostrophe-stripped variant (McDonald's -> mcdonalds)
  - non-ASCII -> ASCII fold (Café -> cafe, Günaydın -> gunaydin)
  - & -> "and" variant (Ben & Jerry's -> ben and jerrys)
  - spacing variants (concatenated + separated)
  - per-chain hardcoded abbreviations

Run:  cd backend && python scripts/audit_aliases.py [--dry-run]
"""
import json
import sys
import unicodedata
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEEDS_DIR = BACKEND / "data" / "chains"
COVERAGE_PATH = BACKEND / "data" / "chain_menu_coverage.json"

# Chain-specific abbreviations. Keyed by chain_key (filename prefix).
HARDCODED_ABBREVS = {
    "mcdonalds": ["mcd", "maccas", "mickey d's", "mickey ds"],
    "burger_king": ["bk"],
    "kfc": ["kfc", "kentucky fried"],
    "dominos": ["dominos pizza"],
    "starbucks": ["sbux"],
    "pizza_hut": ["ph"],
    "dunkin": ["dd", "dunkin donuts", "dunkin' donuts"],
    "cafe_coffee_day": ["ccd"],
    "buffalo_wild_wings": ["bww", "b-dubs"],
    "tgi_fridays": ["tgif"],
    "chick_fil_a": ["cfa", "chick fil a"],
    "a_and_w": ["a&w", "a and w"],
    "chipotle": ["chipotle mexican grill"],
    "shake_shack": ["shake shack"],
    "five_guys": ["five guys"],
    "panera": ["panera bread"],
    "jimmy_johns": ["jj", "jimmy johns"],
    "cpk": ["california pizza kitchen", "cpk"],
    "din_tai_fung": ["dtf"],
    "the_coffee_club": ["coffee club"],
    "in_n_out": ["in n out", "in-n-out burger"],
    "jack_in_the_box": ["jack in box"],
    "pret": ["pret a manger"],
    "pf_changs": ["p.f. chang's", "pf chang's"],
    "carls_jr": ["carl's jr", "carls junior"],
    "moes_southwest": ["moe's", "moes"],
    "jollibee": ["jollibee foods"],
    "mang_inasal": ["inasal"],
    "max_brenner": ["max brenner's"],
    "hungry_jacks": ["hj", "hungry jack"],
    "nandos": ["nando's"],
    "cheesecake_factory": ["the cheesecake factory"],
    "red_robin": ["red robin gourmet burgers"],
    "applebees": ["applebee's"],
    "chilis": ["chili's grill & bar"],
    "papa_johns": ["papa john's pizza"],
    "chowman": ["chow man"],
}


def fold_ascii(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return s.encode("ascii", "ignore").decode("ascii")


def generate_variants(name: str) -> set[str]:
    """Return a set of lowercased alias variants for one input name."""
    out = set()
    n = (name or "").strip()
    if not n:
        return out
    out.add(n.lower())
    # apostrophe-stripped
    no_apos = n.replace("'", "").replace("\u2019", "").replace("`", "")
    out.add(no_apos.lower())
    # ASCII fold
    ascii_n = fold_ascii(n)
    out.add(ascii_n.lower())
    out.add(fold_ascii(no_apos).lower())
    # & -> and
    amp = n.replace("&", " and ").replace("  ", " ")
    out.add(amp.lower())
    out.add(fold_ascii(amp).lower())
    # concatenated (no spaces)
    concat = "".join(n.split())
    out.add(concat.lower())
    # Filter empties
    return {s.strip() for s in out if s and s.strip()}


def expand_aliases(variants: list[str], chain_key: str) -> tuple[list[str], int]:
    """Given existing aliases + chain_key, return expanded list + count added."""
    existing = {v.lower().strip() for v in variants if isinstance(v, str) and v.strip()}
    new_set = set(existing)
    for v in variants:
        if isinstance(v, str):
            new_set |= generate_variants(v)
    # Hardcoded abbreviations
    for abbr in HARDCODED_ABBREVS.get(chain_key, []):
        new_set.add(abbr.lower())
    added = len(new_set) - len(existing)
    # Preserve original order, append new
    final = [v for v in variants if isinstance(v, str)]
    seen_lower = {v.lower().strip() for v in final}
    for v in sorted(new_set):
        if v not in seen_lower:
            final.append(v)
            seen_lower.add(v)
    return final, added


def main():
    dry_run = "--dry-run" in sys.argv

    files = sorted(SEEDS_DIR.glob("*.json"))
    total_added = 0
    files_changed = 0

    # Pass 1: seed files
    for f in files:
        data = json.loads(f.read_text())
        # Filename = {chain_key}_{market}.json
        stem = f.stem
        chain_key, _, _ = stem.rpartition("_")
        original = data.get("store_name_variants") or []
        expanded, added = expand_aliases(list(original), chain_key)
        if added:
            total_added += added
            files_changed += 1
            if not dry_run:
                data["store_name_variants"] = expanded
                with f.open("w", encoding="utf-8") as out:
                    json.dump(data, out, indent=2, ensure_ascii=False)

    print(f"seed files: {len(files)} total, {files_changed} expanded, +{total_added} aliases")

    # Pass 2: coverage.json (chain_aliases field)
    cov = json.loads(COVERAGE_PATH.read_text())
    cov_added = 0
    cov_entries_changed = 0
    for entry in cov.get("chains") or []:
        chain_key = entry.get("chain_key") or ""
        original = entry.get("chain_aliases") or []
        expanded, added = expand_aliases(list(original), chain_key)
        if added:
            cov_added += added
            cov_entries_changed += 1
            entry["chain_aliases"] = expanded
    if cov_added and not dry_run:
        with COVERAGE_PATH.open("w", encoding="utf-8") as out:
            json.dump(cov, out, indent=2, ensure_ascii=False)
    print(f"coverage entries: {cov_entries_changed} expanded, +{cov_added} aliases")

    print(f"\nmode: {'DRY-RUN' if dry_run else 'WRITTEN'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
