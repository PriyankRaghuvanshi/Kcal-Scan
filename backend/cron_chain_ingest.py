"""
Overnight chain ingestion cron job.

Picks thinnest chains, uses Gemini Flash grounded search, validates,
saves new items to SUPABASE (persistent across deploys).
App merges Supabase items with local JSON on startup.

Bulletproof: every chain in try/except, budget-capped, retries with backoff.
"""
from __future__ import annotations

import json
import logging
import os
import requests
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
_TABLE = "cron_ingested_items"


def _sb_url():
    return os.getenv("SUPABASE_URL", "").strip()

def _sb_key():
    return os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

def _sb_headers():
    return {
        "apikey": _sb_key(),
        "Authorization": f"Bearer {_sb_key()}",
        "Content-Type": "application/json",
    }

def _sb_available():
    return bool(_sb_url() and _sb_key())


def _load_ingested() -> Dict[str, Any]:
    if not INGESTED_PATH.exists():
        return {"version": "v1", "chains": {}, "updated_at": ""}
    with INGESTED_PATH.open("r") as f:
        return json.load(f)


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


def _save_items_to_supabase(items: List[Dict[str, Any]], chain_key: str, market: str) -> int:
    """Save validated items to Supabase cron_ingested_items table. Returns count saved."""
    if not _sb_available() or not items:
        return 0

    saved = 0
    for item in items:
        row = {
            "chain_key": chain_key,
            "market": market,
            "item_name": str(item.get("item_name", "")).strip(),
            "estimated_calories": int(float(item.get("estimated_calories") or 0)),
            "estimated_protein_g": round(float(item.get("estimated_protein_g") or 0), 1),
            "estimated_carbs_g": round(float(item.get("estimated_carbs_g") or 0), 1),
            "estimated_fat_g": round(float(item.get("estimated_fat_g") or 0), 1),
            "menu_item_source": str(item.get("menu_item_source") or "real_menu"),
            "category": str(item.get("category") or "").strip(),
            "raw_payload": json.dumps(item),
        }
        cal = row["estimated_calories"]
        pro = row["estimated_protein_g"]
        if cal > 0:
            row["protein_per_100kcal"] = round(pro / (cal / 100), 1)

        try:
            r = requests.post(
                f"{_sb_url()}/rest/v1/{_TABLE}",
                headers={**_sb_headers(), "Prefer": "return=minimal,resolution=ignore-duplicates"},
                params={"on_conflict": "chain_key,market,item_name"},
                data=json.dumps(row),
                timeout=10,
            )
            if r.status_code in (200, 201, 409):
                saved += 1
        except Exception as e:
            logger.warning("Failed to save item %s to Supabase: %s", row.get("item_name"), e)

    return saved


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
    parts = chain_market.split("::")
    chain_key = parts[0]
    market = parts[1] if len(parts) > 1 else ""

    try:
        from tools.ingest_chain_from_url import (
            EXTRACTION_PROMPT,
            MODEL,
            normalize_item,
            parse_json_array,
            validate_items,
        )
    except ImportError:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent / "tools"))
        from ingest_chain_from_url import (
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
            return {"ok": False, "error": f"Gemini failed: {e}", "items_added": 0}

    items = parse_json_array(text)
    if not items:
        return {"ok": False, "error": "No items parsed", "items_added": 0}

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

    # Save to Supabase (persistent!)
    saved = _save_items_to_supabase(valid, chain_key, market)

    # Also save to local JSON (for current server instance)
    existing = data.get("chains", {}).get(chain_market, [])
    existing_names = {str(it.get("item_name", "")).strip().lower() for it in existing}
    local_added = 0
    for item in valid:
        name = str(item.get("item_name", "")).strip().lower()
        if name and name not in existing_names:
            existing.append(item)
            existing_names.add(name)
            local_added += 1

    if local_added > 0:
        data.setdefault("chains", {})[chain_market] = existing

    return {"ok": True, "items_added": saved, "items_local": local_added, "total_parsed": len(valid)}


def load_supabase_cron_items() -> Dict[str, List[Dict[str, Any]]]:
    """Load all cron-ingested items from Supabase, grouped by chain::market."""
    if not _sb_available():
        return {}

    try:
        r = requests.get(
            f"{_sb_url()}/rest/v1/{_TABLE}",
            headers=_sb_headers(),
            params={"select": "*", "limit": "10000"},
            timeout=15,
        )
        if r.status_code != 200:
            return {}

        rows = r.json() or []
        grouped = {}
        for row in rows:
            ck = f"{row.get('chain_key', '')}::{row.get('market', '')}"
            if ck not in grouped:
                grouped[ck] = []
            grouped[ck].append({
                "item_name": row.get("item_name", ""),
                "estimated_calories": row.get("estimated_calories", 0),
                "estimated_protein_g": row.get("estimated_protein_g", 0),
                "estimated_carbs_g": row.get("estimated_carbs_g", 0),
                "estimated_fat_g": row.get("estimated_fat_g", 0),
                "menu_item_source": row.get("menu_item_source", "real_menu"),
                "category": row.get("category", ""),
                "protein_per_100kcal": row.get("protein_per_100kcal", 0),
                "chain_key": row.get("chain_key", ""),
                "market": row.get("market", ""),
            })
        return grouped
    except Exception as e:
        logger.warning("Failed to load cron items from Supabase: %s", e)
        return {}


def merge_supabase_items_into_data(data: Dict[str, Any]) -> int:
    """Merge Supabase cron items into the chain data. Returns count of new items added."""
    sb_items = load_supabase_cron_items()
    if not sb_items:
        return 0

    added = 0
    for ck, items in sb_items.items():
        existing = data.setdefault("chains", {}).get(ck, [])
        existing_names = {str(it.get("item_name", "")).strip().lower() for it in existing}
        for item in items:
            name = str(item.get("item_name", "")).strip().lower()
            if name and name not in existing_names:
                existing.append(item)
                existing_names.add(name)
                added += 1
        data["chains"][ck] = existing

    if added > 0:
        logger.info("Merged %d cron-ingested items from Supabase", added)

    return added


def run_cron_ingest() -> Dict[str, Any]:
    start = time.time()
    data = _load_ingested()

    # Merge any existing Supabase items first
    merge_supabase_items_into_data(data)

    fail_log = _load_fail_log()
    targets = _get_thinnest_chains(data, fail_log, MAX_CHAINS_PER_RUN)

    if not targets:
        return {"status": "no_targets", "message": "All chains have 25+ items or in cooldown"}

    results = []
    total_added = 0
    total_cost = 0.0
    succeeded = 0
    failed = 0

    for i, chain_market in enumerate(targets):
        if total_cost >= MAX_BUDGET_USD:
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
                entry = fail_log.get(chain_market, {"consecutive_fails": 0})
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

        if i < len(targets) - 1 and total_cost < MAX_BUDGET_USD:
            time.sleep(DELAY_BETWEEN_CHAINS)

    _save_fail_log(fail_log)

    total_items = sum(len(v) for v in data.get("chains", {}).values() if isinstance(v, list))
    elapsed = round(time.time() - start, 1)

    return {
        "status": "completed",
        "chains_processed": succeeded + failed,
        "succeeded": succeeded,
        "failed": failed,
        "items_added_to_supabase": total_added,
        "estimated_cost_usd": round(total_cost, 3),
        "total_items_in_db": total_items,
        "elapsed_seconds": elapsed,
        "results": results[:20],
    }
