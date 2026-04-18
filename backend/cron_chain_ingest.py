"""
Overnight chain ingestion cron job.

Runs on Railway as a scheduled endpoint. Picks the thinnest chains,
uses Gemini Flash grounded search to find real menu items, validates,
and commits to chain_menu_ingested.json.

Bulletproof: every chain wrapped in try/except, budget-capped,
retries with backoff, skips recently failed chains.

Triggered via: POST /admin/cron/chain-ingest
Or Railway cron: curl -X POST https://your-app.up.railway.app/admin/cron/chain-ingest
"""
from __future__ import annotations

import json
import logging
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

INGESTED_PATH = Path(__file__).resolve().parent / "data" / "chain_menu_ingested.json"
FAIL_LOG_PATH = Path(__file__).resolve().parent / "data" / "cron_ingest_failures.json"

MAX_BUDGET_USD = float(os.getenv("CRON_INGEST_BUDGET", "2.00"))
COST_PER_CHAIN_USD = 0.03
MAX_CHAINS_PER_RUN = int(MAX_BUDGET_USD / COST_PER_CHAIN_USD)
MIN_ITEMS_THRESHOLD = 8
DELAY_BETWEEN_CHAINS = 6
MAX_RETRIES = 2
RETRY_BACKOFF = 10


def _load_ingested() -> Dict[str, Any]:
    if not INGESTED_PATH.exists():
        return {"version": "v1", "chains": {}, "updated_at": ""}
    with INGESTED_PATH.open("r") as f:
        return json.load(f)


def _save_ingested(data: Dict[str, Any]) -> None:
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with INGESTED_PATH.open("w") as f:
        json.dump(data, f)


def _load_fail_log() -> Dict[str, Any]:
    if not FAIL_LOG_PATH.exists():
        return {}
    try:
        with FAIL_LOG_PATH.open("r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_fail_log(log: Dict[str, Any]) -> None:
    FAIL_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FAIL_LOG_PATH.open("w") as f:
        json.dump(log, f, indent=2)


def _get_thinnest_chains(data: Dict[str, Any], fail_log: Dict[str, Any], limit: int) -> List[str]:
    chains = data.get("chains", {})
    candidates = []
    for ck, items in chains.items():
        if not isinstance(items, list):
            continue
        count = len(items)
        if count >= 25:
            continue
        if count < 1:
            continue
        fails = fail_log.get(ck, {}).get("consecutive_fails", 0)
        if fails >= 3:
            continue
        candidates.append((ck, count, fails))
    candidates.sort(key=lambda x: (x[1], x[2]))
    return [c[0] for c in candidates[:limit]]


def _ingest_one_chain(chain_market: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Ingest one chain using Gemini grounded search. Returns result dict."""
    parts = chain_market.split("::")
    chain_key = parts[0]
    market = parts[1] if len(parts) > 1 else ""

    from tools.ingest_chain_from_url import (
        EXTRACTION_PROMPT,
        MODEL,
        normalize_item,
        parse_json_array,
        validate_items,
    )
    import google.generativeai as genai

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        return {"ok": False, "error": "GEMINI_API_KEY not set", "items_added": 0}

    genai.configure(api_key=api_key)

    prompt = EXTRACTION_PROMPT.format(
        chain_key=chain_key,
        market=market or "global",
        existing_count=len(data.get("chains", {}).get(chain_market, [])),
    )

    model = genai.GenerativeModel(
        MODEL,
        tools="google_search_retrieval",
    )

    for attempt in range(MAX_RETRIES + 1):
        try:
            response = model.generate_content(prompt)
            text = response.text or ""
            break
        except Exception as e:
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_BACKOFF * (attempt + 1))
                continue
            return {"ok": False, "error": f"Gemini failed after {MAX_RETRIES + 1} attempts: {e}", "items_added": 0}

    items = parse_json_array(text)
    if not items:
        return {"ok": False, "error": "No items parsed from response", "items_added": 0}

    normalized = []
    for raw in items:
        try:
            norm = normalize_item(raw, chain_key=chain_key, market=market)
            if norm:
                normalized.append(norm)
        except Exception:
            continue

    valid, _ = validate_items(normalized, chain_key=chain_key, market=market)
    if not valid:
        return {"ok": False, "error": "No items passed validation", "items_added": 0}

    existing = data.get("chains", {}).get(chain_market, [])
    existing_names = {str(it.get("item_name", "")).strip().lower() for it in existing}
    added = 0
    for item in valid:
        name = str(item.get("item_name", "")).strip().lower()
        if name and name not in existing_names:
            existing.append(item)
            existing_names.add(name)
            added += 1

    if added > 0:
        data.setdefault("chains", {})[chain_market] = existing

    return {"ok": True, "items_added": added, "total_parsed": len(valid)}


def run_cron_ingest() -> Dict[str, Any]:
    """Main entry point for the cron job."""
    start = time.time()
    data = _load_ingested()
    fail_log = _load_fail_log()

    targets = _get_thinnest_chains(data, fail_log, MAX_CHAINS_PER_RUN)
    if not targets:
        return {"status": "no_targets", "message": "All chains have 25+ items or are in cooldown"}

    results = []
    total_added = 0
    total_cost = 0.0
    succeeded = 0
    failed = 0

    for i, chain_market in enumerate(targets):
        if total_cost >= MAX_BUDGET_USD:
            logger.info("Budget cap reached ($%.2f), stopping", total_cost)
            break

        logger.info("[%d/%d] Processing %s", i + 1, len(targets), chain_market)

        try:
            result = _ingest_one_chain(chain_market, data)
            total_cost += COST_PER_CHAIN_USD

            if result.get("ok"):
                total_added += result.get("items_added", 0)
                succeeded += 1
                fail_log.pop(chain_market, None)
                results.append({"chain": chain_market, "status": "ok", "added": result["items_added"]})
            else:
                failed += 1
                entry = fail_log.get(chain_market, {"consecutive_fails": 0, "last_error": ""})
                entry["consecutive_fails"] = entry.get("consecutive_fails", 0) + 1
                entry["last_error"] = result.get("error", "unknown")
                entry["last_attempt"] = datetime.now(timezone.utc).isoformat()
                fail_log[chain_market] = entry
                results.append({"chain": chain_market, "status": "failed", "error": result.get("error", "")})

        except Exception as e:
            failed += 1
            entry = fail_log.get(chain_market, {"consecutive_fails": 0})
            entry["consecutive_fails"] = entry.get("consecutive_fails", 0) + 1
            entry["last_error"] = str(e)[:200]
            entry["last_attempt"] = datetime.now(timezone.utc).isoformat()
            fail_log[chain_market] = entry
            results.append({"chain": chain_market, "status": "exception", "error": str(e)[:200]})
            logger.error("Exception processing %s: %s", chain_market, traceback.format_exc())

        if i < len(targets) - 1 and total_cost < MAX_BUDGET_USD:
            time.sleep(DELAY_BETWEEN_CHAINS)

    if total_added > 0:
        _save_ingested(data)

    _save_fail_log(fail_log)

    total_items = sum(len(v) for v in data.get("chains", {}).values() if isinstance(v, list))
    elapsed = round(time.time() - start, 1)

    summary = {
        "status": "completed",
        "chains_processed": succeeded + failed,
        "succeeded": succeeded,
        "failed": failed,
        "items_added": total_added,
        "estimated_cost_usd": round(total_cost, 3),
        "total_items_in_db": total_items,
        "elapsed_seconds": elapsed,
        "results": results,
    }

    logger.info("Cron ingest complete: %d added, %d succeeded, %d failed, $%.3f cost",
                total_added, succeeded, failed, total_cost)

    return summary
