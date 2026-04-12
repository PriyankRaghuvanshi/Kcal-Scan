#!/usr/bin/env python3
"""
Audit confidence scores across all seed files.

Many seeds default to confidence=0.82. This flags outliers that may
need manual review — items below 0.7 (low-confidence sources) or
identical scores across a whole chain (suggests no differentiation
between exact menu items vs. estimates).

Run: cd backend && python scripts/audit_confidence_scores.py
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
SEEDS_DIR = BACKEND / "data" / "chains"


def main():
    files = sorted(SEEDS_DIR.glob("*.json"))

    all_confidences = []
    low_confidence_items = []  # < 0.7
    uniform_chains = []  # all items same confidence
    missing_confidence = []  # no confidence field

    for f in files:
        data = json.loads(f.read_text())
        items = data.get("items") or []
        confidences = []
        for item in items:
            if not isinstance(item, dict):
                continue
            c = item.get("confidence")
            if c is None:
                missing_confidence.append(f"{f.stem} :: {item.get('item_name')}")
                continue
            confidences.append(c)
            all_confidences.append(c)
            if c < 0.7:
                low_confidence_items.append(f"{f.stem} :: {item.get('item_name')} @ {c}")

        if len(confidences) > 1 and len(set(confidences)) == 1:
            uniform_chains.append((f.stem, confidences[0], len(confidences)))

    total = len(all_confidences)
    avg = sum(all_confidences) / total if total else 0

    buckets = Counter()
    for c in all_confidences:
        if c < 0.5:
            buckets["<0.50"] += 1
        elif c < 0.7:
            buckets["0.50-0.69"] += 1
        elif c < 0.8:
            buckets["0.70-0.79"] += 1
        elif c < 0.9:
            buckets["0.80-0.89"] += 1
        else:
            buckets["0.90+"] += 1

    print(f"=== CONFIDENCE AUDIT ({total} items in {len(files)} seed files) ===")
    print(f"average confidence: {avg:.3f}")
    print(f"\ndistribution:")
    for k, v in sorted(buckets.items()):
        pct = 100 * v / total
        bar = "█" * int(pct / 2)
        print(f"  {k:<12} {v:>5} ({pct:5.1f}%)  {bar}")

    print(f"\nlow-confidence items (<0.7): {len(low_confidence_items)}")
    for x in low_confidence_items[:10]:
        print(f"  {x}")
    if len(low_confidence_items) > 10:
        print(f"  ... {len(low_confidence_items) - 10} more")

    print(f"\nchains with uniform confidence (all items same score): {len(uniform_chains)}")
    top_uniform = Counter(conf for _, conf, _ in uniform_chains).most_common(5)
    print(f"  most common uniform scores:")
    for conf, n in top_uniform:
        print(f"    conf={conf}: {n} chains")
    print(f"  (these are places where we could differentiate exact items from estimates)")

    print(f"\nitems missing confidence: {len(missing_confidence)}")
    for x in missing_confidence[:5]:
        print(f"  {x}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
