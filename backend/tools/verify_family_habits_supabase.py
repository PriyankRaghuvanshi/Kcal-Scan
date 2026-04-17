from __future__ import annotations

import json
import os
import sys
from typing import Dict, List

import requests


FAMILY_HABITS_TABLES = [
    "households",
    "household_members",
    "children",
    "child_safe_foods",
    "child_target_foods",
    "meals_served",
    "meal_components",
    "child_meal_outcomes",
    "food_exposures",
    "routine_signals",
    "rescue_sessions",
    "weekly_resets",
    "family_meal_memory",
]


def _env(name: str) -> str:
    return str(os.getenv(name) or "").strip()


def _headers() -> Dict[str, str]:
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
    }


def check_table(base_url: str, table: str) -> Dict[str, str]:
    url = f"{base_url}/rest/v1/{table}"
    res = requests.get(url, headers=_headers(), params={"select": "*", "limit": "1"}, timeout=20)
    body = res.text.strip()
    if res.ok:
        return {"table": table, "status": "present", "raw": body[:240]}
    if "PGRST205" in body and "Could not find the table" in body:
        return {"table": table, "status": "missing", "raw": body[:240]}
    return {"table": table, "status": f"http_{res.status_code}", "raw": body[:240]}


def main() -> int:
    base_url = _env("SUPABASE_URL")
    service_key = _env("SUPABASE_SERVICE_ROLE_KEY")
    if not base_url or not service_key:
        print(json.dumps({"ok": False, "error": "missing_supabase_env"}, indent=2))
        return 1

    results: List[Dict[str, str]] = [check_table(base_url, table) for table in FAMILY_HABITS_TABLES]
    missing = [row["table"] for row in results if row["status"] == "missing"]
    out = {
        "ok": True,
        "base_url": base_url,
        "tables": results,
        "missing_tables": missing,
        "migration_hint": "Apply backend/family_habits_schema.sql in the Supabase SQL Editor or your linked DB workflow.",
    }
    print(json.dumps(out, indent=2))
    return 0 if not missing else 2


if __name__ == "__main__":
    sys.exit(main())
