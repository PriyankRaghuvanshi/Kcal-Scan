#!/usr/bin/env python3
"""
Fix portion/calorie mismatch on pizza items.

Problem: many seeds have items like "Grilled Chicken Personal" with
~540 kcal. A personal pizza is a *whole small pizza* (~1600 kcal). The
540 figure is realistic only for ~2 slices of a personal, so the label
is silently under-reporting calories by ~3x.

Fix strategy (rename, don't rescale):
  - Keep the calorie number — it's honest for a 2-slice portion
  - Rename the item so the portion matches the number, matching the
    pizza_hut_us / pizza_hut_in "(2 slices, thin)" convention that users
    already trust.

Targets: any pizza-like item (name contains pizza|personal|whole) that
  - does NOT already specify a slice/kg portion
  - has 0 < estimated_calories < 800 (i.e. too low for a whole pizza)

Idempotent. Dry-run by default.
"""
import argparse
import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "chains"

PIZZA_NAME_RE = re.compile(r"(pizza|personal|whole)", re.I)
ALREADY_PORTIONED_RE = re.compile(r"(slice|slices|kg|grams?|\bml\b|serving)", re.I)

# Items to skip entirely — not sliced pizzas, even though the name contains "Pizza".
# Example: Taco Bell Mexican Pizza is a whole 2-tortilla dish (~540 kcal whole),
# not cut into slices. Tagging "(2 slices)" would halve the real intake.
SKIP_EXACT = {
    ("taco_bell_us", "Mexican Pizza"),
}

# Chains where pizzas are individual small pies, often eaten whole as one serving.
# For these, use "(1 serving, small)" rather than "(2 slices)" so we don't
# imply half-a-pie when the listed kcal is the full pie.
INDIVIDUAL_PIE_CHAINS = {
    "blaze_pizza_us",
    "pizza_pilgrims_gb",
    "losteria_de",
    "rossopomodoro_it",
    "vapiano_de",
    "vapiano_it",
    "toit_in",
    "mellow_mushroom_us",
}

# Name rewrites for "(2 slices, personal)" style:
#   "X Personal Pizza"   -> "X (2 slices, personal)"
#   "X (personal)"        -> "X (2 slices, personal)"
#   "X Personal"          -> "X (2 slices, personal)"
#   "Personal Pan X"      -> "X (2 slices, personal pan)"
REWRITES_SLICES = [
    (re.compile(r"\s+Personal\s+Pizza\b", re.I), " (2 slices, personal)"),
    (re.compile(r"\s*\(personal\)\s*$", re.I), " (2 slices, personal)"),
    (re.compile(r"\s+Personal\b", re.I), " (2 slices, personal)"),
    (re.compile(r"^Personal\s+Pan\s+(.+)$", re.I), r"\1 (2 slices, personal pan)"),
]


def rewrite_name(name: str, individual_pie: bool = False) -> str:
    """Return the renamed form, or the original if no rule fires."""
    if individual_pie:
        # For individual-pie chains, just append "(1 serving, small)" without
        # claiming a slice count that might halve real intake.
        if "(" in name:
            return name
        return name + " (1 serving, small)"
    new = name
    for pat, repl in REWRITES_SLICES:
        candidate = pat.sub(repl, new)
        if candidate != new:
            return re.sub(r"\s+", " ", candidate).strip()
    # Plain "X Pizza" with under-800 cal: add slice hint without guessing size
    if re.search(r"\bPizza\b", new) and "(" not in new:
        return new + " (2 slices)"
    return new


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="Persist changes (default: dry-run).")
    args = ap.parse_args()

    touched_files = 0
    touched_items = 0
    preview = []
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            with path.open() as f:
                data = json.load(f)
        except Exception:
            continue
        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            continue
        changed = False
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("item_name") or "").strip()
            cal = int(it.get("estimated_calories") or 0)
            if not (0 < cal < 800):
                continue
            if not PIZZA_NAME_RE.search(name):
                continue
            if ALREADY_PORTIONED_RE.search(name):
                continue
            if (path.stem, name) in SKIP_EXACT:
                continue
            new_name = rewrite_name(name, individual_pie=path.stem in INDIVIDUAL_PIE_CHAINS)
            if new_name != name:
                preview.append((path.stem, name, new_name, cal))
                it["item_name"] = new_name
                touched_items += 1
                changed = True
        if changed:
            touched_files += 1
            if args.write:
                with path.open("w") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.write("\n")

    mode = "written" if args.write else "dry-run"
    print(f"{mode}: renamed {touched_items} items across {touched_files} files")
    for stem, old, new, cal in preview[:30]:
        print(f"  {stem:<28} {cal:>4} kcal  {old!r} -> {new!r}")
    if len(preview) > 30:
        print(f"  ... and {len(preview) - 30} more")


if __name__ == "__main__":
    main()
