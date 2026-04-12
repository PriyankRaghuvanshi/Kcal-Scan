#!/usr/bin/env python3
"""
Quarterly refresh: use Claude API to update chain menu items.

Reads each seed file, asks Claude to verify/refresh items against the chain's
current public menu, and writes updates. Meant to run on a cron (quarterly) to
keep chain data current as menus evolve.

Uses prompt caching to keep cost reasonable — the audit guidelines are cached
once per run and reused across all chains.

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    cd backend
    python scripts/quarterly_refresh.py [--dry-run] [--chain CHAIN_KEY] [--market MARKET] [--limit N]

Flags:
    --dry-run           Don't write; just log what would change.
    --chain CHAIN_KEY   Only refresh this chain_key.
    --market MARKET     Only refresh this 2-letter market.
    --limit N           Stop after N chains (for testing / cost control).
    --force             Refresh even if seed was updated recently.

Output:
    data/refresh_log.json — per-run summary of changes.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BACKEND = Path(__file__).resolve().parent.parent
SEEDS_DIR = BACKEND / "data" / "chains"
LOG_PATH = BACKEND / "data" / "refresh_log.json"

MODEL = "claude-sonnet-4-5"  # fast, cost-efficient; bump to opus if accuracy issues
MAX_TOKENS = 2000

SYSTEM_PROMPT = """\
You are a nutrition data auditor for a calorie-tracking app. You verify that a \
chain restaurant's menu items + nutrition data are still accurate against the \
chain's current public menu.

Given one chain (brand name, market/country, source URL, current seeded items), \
output a JSON object with:
  "status": "unchanged" | "updated" | "skip" (skip only if chain closed/unverifiable)
  "updated_items": array — the full refreshed item list (same shape as input). \
Omit if status != "updated".
  "notes": brief string explaining what changed or why unchanged.

Rules:
- Preserve halal_possible and gluten_free_possible fields per-item.
- Only refresh if real menu changes. Don't fiddle with calorie estimates within ±5%.
- Add removed items (menu changes) or drop discontinued items.
- If chain no longer operates in this market, return status="skip".
- If unsure, return status="unchanged".
- Always return valid JSON — no prose before/after.
"""


def read_log() -> dict:
    if LOG_PATH.exists():
        try:
            return json.loads(LOG_PATH.read_text())
        except Exception:
            pass
    return {"runs": []}


def write_log(log: dict) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


def refresh_one(client, seed_path: Path, seed: dict) -> tuple[str, dict, str]:
    """Call Claude for one seed. Returns (status, maybe_updated_items, notes)."""
    stem = seed_path.stem  # chain_key_market
    chain_key, _, market = stem.rpartition("_")
    payload = {
        "chain_key": chain_key,
        "market": market.upper(),
        "brand_name": seed.get("brand_name"),
        "source_url": seed.get("source_url"),
        "current_items": seed.get("items") or [],
    }
    user_text = (
        "Refresh this chain's menu items against the current public menu. "
        "Respond with JSON only per the schema in the system prompt.\n\n"
        + json.dumps(payload, indent=2, ensure_ascii=False)
    )

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_text}],
    )
    raw = resp.content[0].text.strip()
    # Strip fenced code block if present
    if raw.startswith("```"):
        raw = raw.split("```", 2)[-2 if raw.count("```") >= 2 else -1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        return "error", {}, f"parse error: {e} | raw={raw[:200]}"

    status = parsed.get("status", "unchanged")
    updated_items = parsed.get("updated_items") or []
    notes = parsed.get("notes", "")
    return status, updated_items, notes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--chain", help="Only refresh this chain_key")
    parser.add_argument("--market", help="Only refresh this market code (e.g. US)")
    parser.add_argument("--limit", type=int, default=0, help="Stop after N chains")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set", file=sys.stderr)
        return 2

    # Lazy import so script loads even without anthropic installed
    try:
        from anthropic import Anthropic
    except ImportError:
        print("ERROR: pip install anthropic", file=sys.stderr)
        return 2

    client = Anthropic(api_key=api_key)

    files = sorted(SEEDS_DIR.glob("*.json"))
    targets = []
    for f in files:
        stem = f.stem
        chain_key, _, market = stem.rpartition("_")
        if args.chain and chain_key != args.chain:
            continue
        if args.market and market.lower() != args.market.lower():
            continue
        targets.append(f)
    if args.limit:
        targets = targets[: args.limit]

    run_started = datetime.now(timezone.utc).isoformat()
    print(f"refreshing {len(targets)} chains at {run_started}")

    changes = {"unchanged": 0, "updated": 0, "skip": 0, "error": 0}
    per_chain = []

    for i, f in enumerate(targets, 1):
        seed = json.loads(f.read_text())
        try:
            status, updated_items, notes = refresh_one(client, f, seed)
        except Exception as e:
            status, updated_items, notes = "error", [], f"exception: {e}"

        changes[status] = changes.get(status, 0) + 1
        log_entry = {"file": f.name, "status": status, "notes": notes}
        per_chain.append(log_entry)

        print(f"  [{i}/{len(targets)}] {f.stem:<40} {status:<10} {notes[:80]}")

        if status == "updated" and updated_items and not args.dry_run:
            seed["items"] = updated_items
            seed["_last_refreshed"] = run_started
            with f.open("w", encoding="utf-8") as out:
                json.dump(seed, out, indent=2, ensure_ascii=False)
        time.sleep(0.3)  # gentle rate limit

    # Append to log
    log = read_log()
    log["runs"].append({
        "run_started": run_started,
        "chains_processed": len(targets),
        "summary": changes,
        "dry_run": args.dry_run,
        "filters": {"chain": args.chain, "market": args.market, "limit": args.limit},
        "per_chain": per_chain[:50],  # cap log size
    })
    log["runs"] = log["runs"][-20:]  # keep last 20 runs
    write_log(log)

    print(f"\nsummary: {changes}")
    print(f"(if any updated: run `python scripts/merge_chain_seeds_to_registry.py --force` to propagate)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
