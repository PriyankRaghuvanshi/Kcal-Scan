#!/usr/bin/env python3
"""
Run chain menu ingestion for all first 10 chains.
Background job - no live fetch. Populates chain_menu_ingested.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from chain_menu_ingestion import run_ingestion_all


def main() -> None:
    result = run_ingestion_all(market_tag="AU", max_items_per_chain=30)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
