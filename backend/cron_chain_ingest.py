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
    """DISABLED 2026-05-08: this used to call Gemini 2.5 Flash with grounded
    search to extract menu items per chain::market. The deterministic crawler
    + pdfplumber pipeline (tools/ingest_chain_from_url.py + ingest_chain_from_pdf.py)
    replaces it. We keep the function symbol so main.py and run_cron_ingest()
    don't crash on import, but it short-circuits with a clear error and never
    touches the Gemini SDK.
    """
    return {
        "ok": False,
        "error": ("cron_chain_ingest._ingest_one_chain is disabled — Gemini "
                  "ingestion path is retired. Use tools/reingest_cached_pdfs.py "
                  "or tools/ingest_chain_from_pdf.py instead."),
        "items_added": 0,
    }


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
    """DISABLED 2026-05-08: this used to drive the Gemini-grounded chain
    ingestion across thinnest chains. Replaced by the deterministic pipeline
    (tools/ingest_chain_from_url.py + tools/reingest_cached_pdfs.py). The
    admin endpoint POST /admin/cron/chain-ingest still calls this, but it
    now short-circuits without spending any money. To re-enable, set
    KCAL_ALLOW_LEGACY_GEMINI_CRON=1 — but you almost certainly want to run
    the deterministic tools instead."""
    if os.getenv("KCAL_ALLOW_LEGACY_GEMINI_CRON", "").strip() != "1":
        return {
            "status": "disabled",
            "message": ("Legacy Gemini cron is disabled. Use "
                        "tools/reingest_cached_pdfs.py for cached PDFs or "
                        "tools/ingest_chain_from_url.py for live crawl. "
                        "Set KCAL_ALLOW_LEGACY_GEMINI_CRON=1 to re-enable "
                        "(NOT recommended)."),
            "chains_processed": 0,
            "succeeded": 0,
            "failed": 0,
            "items_added_to_supabase": 0,
            "estimated_cost_usd": 0.0,
            "results": [],
        }
    # Escape hatch: original behavior, kept for emergency override only.
    return {
        "status": "disabled_no_implementation",
        "message": ("Legacy Gemini cron logic was removed in the "
                    "deterministic pivot. KCAL_ALLOW_LEGACY_GEMINI_CRON "
                    "is set, but there's nothing to fall back to. Restore "
                    "from git history at commit 32582208^ if absolutely "
                    "needed."),
    }
