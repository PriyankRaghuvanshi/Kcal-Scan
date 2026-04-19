"""
Menu Piggyback — extract menu items from restaurant websites during Healthy Nearby.

When Google Places returns a websiteUri for a restaurant, we check if it has
menu/nutrition data. If found, items are saved to Supabase for permanent storage.
Runs async in background — doesn't slow down the main response.

Cost: $0 (no extra API calls — uses websiteUri already returned by Google Places)
"""
from __future__ import annotations

import json
import logging
import os
import re
import requests
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

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


def extract_menu_items_from_website(url: str, place_name: str = "") -> List[Dict[str, Any]]:
    """
    Try to extract menu items from a restaurant's website.
    Looks for common patterns: menu pages, nutrition info, structured data.
    Returns list of {item_name, estimated_calories, ...} or empty list.
    """
    if not url or not url.startswith("http"):
        return []

    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (compatible; CalorieClick/1.0; +https://calorieclick.ai)",
            "Accept": "text/html",
        }
        r = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        if r.status_code != 200:
            return []

        html = r.text[:50000]  # limit to 50KB

        # Look for JSON-LD structured data (Schema.org Menu)
        items = _extract_jsonld_menu(html, place_name)
        if items:
            return items

        # Look for common menu patterns in HTML
        items = _extract_html_menu_items(html, place_name)
        return items

    except Exception as e:
        logger.debug("Menu piggyback failed for %s: %s", url, e)
        return []


def _extract_jsonld_menu(html: str, place_name: str) -> List[Dict[str, Any]]:
    """Extract menu items from JSON-LD structured data (Schema.org)."""
    items = []
    try:
        # Find all JSON-LD blocks
        pattern = r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>'
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)

        for match in matches:
            try:
                data = json.loads(match)
                if isinstance(data, list):
                    for d in data:
                        items.extend(_parse_schema_menu(d, place_name))
                elif isinstance(data, dict):
                    items.extend(_parse_schema_menu(data, place_name))
            except json.JSONDecodeError:
                continue
    except Exception:
        pass
    return items[:50]  # cap at 50 items


def _parse_schema_menu(data: dict, place_name: str) -> List[Dict[str, Any]]:
    """Parse Schema.org Menu/MenuItem structures."""
    items = []
    schema_type = str(data.get("@type", "")).lower()

    if schema_type == "menu":
        sections = data.get("hasMenuSection", [])
        if isinstance(sections, dict):
            sections = [sections]
        for section in sections:
            if isinstance(section, dict):
                menu_items = section.get("hasMenuItem", [])
                if isinstance(menu_items, dict):
                    menu_items = [menu_items]
                for mi in menu_items:
                    if isinstance(mi, dict):
                        name = str(mi.get("name", "")).strip()
                        if name and len(name) > 2:
                            items.append({"item_name": name, "source": "schema_org"})

    elif schema_type == "restaurant":
        menu = data.get("hasMenu", {})
        if isinstance(menu, dict):
            items.extend(_parse_schema_menu(menu, place_name))
        elif isinstance(menu, list):
            for m in menu:
                if isinstance(m, dict):
                    items.extend(_parse_schema_menu(m, place_name))

    return items


def _extract_html_menu_items(html: str, place_name: str) -> List[Dict[str, Any]]:
    """Extract menu item names from common HTML patterns."""
    items = []

    # Look for common menu item patterns
    patterns = [
        r'class="[^"]*menu[_-]?item[_-]?name[^"]*"[^>]*>([^<]{3,60})<',
        r'class="[^"]*dish[_-]?name[^"]*"[^>]*>([^<]{3,60})<',
        r'class="[^"]*item[_-]?title[^"]*"[^>]*>([^<]{3,60})<',
        r'<h[34][^>]*class="[^"]*menu[^"]*"[^>]*>([^<]{3,60})<',
    ]

    seen = set()
    for pattern in patterns:
        matches = re.findall(pattern, html, re.IGNORECASE)
        for match in matches:
            name = match.strip()
            if name.lower() not in seen and len(name) > 2 and not name.startswith("<"):
                seen.add(name.lower())
                items.append({"item_name": name, "source": "html_scrape"})

    return items[:30]


def save_piggyback_items_to_supabase(
    items: List[Dict[str, Any]],
    place_name: str,
    place_id: str = "",
    area_key: str = "",
) -> int:
    """Save extracted menu item names to Supabase. Macros estimated later."""
    if not _sb_url() or not _sb_key() or not items:
        return 0

    saved = 0
    chain_key = re.sub(r'[^a-z0-9]+', '_', place_name.lower().strip())[:40]

    for item in items:
        name = str(item.get("item_name", "")).strip()
        if not name or len(name) < 3:
            continue

        row = {
            "chain_key": chain_key,
            "market": area_key.split("_")[-1].upper() if area_key else "UNKNOWN",
            "item_name": name,
            "estimated_calories": 0,
            "estimated_protein_g": 0,
            "estimated_carbs_g": 0,
            "estimated_fat_g": 0,
            "menu_item_source": "website_piggyback",
            "category": "",
            "raw_payload": json.dumps({"place_name": place_name, "place_id": place_id, "source": item.get("source", "")}),
        }

        try:
            r = requests.post(
                f"{_sb_url()}/rest/v1/{_TABLE}",
                headers={**_sb_headers(), "Prefer": "return=minimal,resolution=ignore-duplicates"},
                params={"on_conflict": "chain_key,market,item_name"},
                data=json.dumps(row),
                timeout=5,
            )
            if r.status_code in (200, 201, 409):
                saved += 1
        except Exception:
            pass

    if saved > 0:
        logger.info("Piggyback: saved %d menu items from %s", saved, place_name)

    return saved


def piggyback_extract_async(places: List[Dict[str, Any]], area_key: str = ""):
    """
    Run menu extraction in background for all places with websiteUri.
    Called after Healthy Nearby returns results — doesn't slow response.
    """
    def _run():
        for place in places:
            website = str(place.get("website") or place.get("websiteUri") or "").strip()
            name = str(place.get("place_name") or place.get("name") or "").strip()
            place_id = str(place.get("place_id") or place.get("id") or "").strip()

            if not website or not name:
                continue

            items = extract_menu_items_from_website(website, name)
            if items:
                save_piggyback_items_to_supabase(items, name, place_id, area_key)

    threading.Thread(target=_run, daemon=True, name="menu-piggyback").start()
