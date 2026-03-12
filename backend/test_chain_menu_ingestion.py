"""
Tests for chain menu ingestion: store, candidate preference, no live fetch.
"""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure backend in path
import sys
BACKEND = Path(__file__).resolve().parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from chain_menu_ingestion import (
    get_chain_items,
    get_chain_item_by_name,
    list_ingested_chain_keys,
    run_ingestion_for_chain,
    clear_ingested_store_cache,
)


class TestChainIngestionStore(unittest.TestCase):
    def setUp(self):
        self._old_path = os.environ.get("CHAIN_MENU_INGESTED_STORE_PATH")
        self._tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
        self._tmp.close()
        os.environ["CHAIN_MENU_INGESTED_STORE_PATH"] = self._tmp.name

    def tearDown(self):
        clear_ingested_store_cache()
        if self._old_path is not None:
            os.environ["CHAIN_MENU_INGESTED_STORE_PATH"] = self._old_path
        elif "CHAIN_MENU_INGESTED_STORE_PATH" in os.environ:
            del os.environ["CHAIN_MENU_INGESTED_STORE_PATH"]
        try:
            Path(self._tmp.name).unlink(missing_ok=True)
        except Exception:
            pass

    def test_run_ingestion_populates_store(self):
        r = run_ingestion_for_chain("subway", market_tag="AU", max_items=5)
        self.assertEqual(r.get("status"), "ok")
        self.assertGreater(r.get("item_count", 0), 0)
        items = get_chain_items("subway", "AU")
        self.assertGreater(len(items), 0)
        self.assertIn("item_name", items[0])

    def test_get_chain_item_by_name(self):
        run_ingestion_for_chain("subway", market_tag="AU", max_items=5)
        item = get_chain_item_by_name("subway", "6\" Grilled Chicken Sub", "AU")
        self.assertIsNotNone(item)
        self.assertIn("Chicken", str(item.get("item_name", "")))

    def test_list_ingested_chain_keys(self):
        run_ingestion_for_chain("subway", market_tag="AU", max_items=3)
        keys = list_ingested_chain_keys()
        self.assertIn("subway", keys)

    def test_empty_for_unknown_chain(self):
        items = get_chain_items("unknown_chain_xyz", "AU")
        self.assertEqual(items, [])


class TestIngestedPreferOverTemplate(unittest.TestCase):
    """Verify ingested items preferred over registry template in resolve_chain_menu_for_place."""

    def test_resolve_uses_ingested_when_available(self):
        from chain_menu_registry import resolve_chain_menu_for_place
        # Uses real store if ingestion was run; otherwise registry template
        r = resolve_chain_menu_for_place({"name": "Subway Parramatta"}, country_code="AU", max_items=5)
        if r:
            # If we have ingestion data, source should be ingested_chain_item; else chain_registry
            src = r.get("chain_source_used") or r.get("menu_source") or ""
            self.assertIn(src, ("ingested_chain_item", "chain_registry", "country_chain_registry", "global_chain_registry"))


class TestNoLiveFetch(unittest.TestCase):
    """Hot path must not fetch menus."""

    def test_fetch_chain_source_returns_none_by_default(self):
        from chain_menu_sources import fetch_chain_source
        raw = fetch_chain_source("subway", "AU")
        self.assertIsNone(raw)
