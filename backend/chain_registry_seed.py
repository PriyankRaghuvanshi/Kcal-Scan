from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

from chain_registry import merge_user_chain_records, merge_user_franchise_list


def _load_seed_payload(path: str) -> Dict[str, Any]:
    file_path = Path(path)
    if not file_path.exists():
        return {"chains": [], "franchises": []}
    payload = json.loads(file_path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        chains = payload.get("chains") if isinstance(payload.get("chains"), list) else []
        franchises = payload.get("franchises") if isinstance(payload.get("franchises"), list) else []
        return {"chains": chains, "franchises": franchises}
    if isinstance(payload, list):
        if payload and all(isinstance(row, dict) for row in payload):
            return {"chains": payload, "franchises": []}
        return {"chains": [], "franchises": payload}
    return {"chains": [], "franchises": []}


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge user-provided franchise seed data into global chain registry")
    parser.add_argument("--user-list", required=True, help="Path to JSON seed file (supports {chains:[...]} or list)")
    parser.add_argument("--country", default="GLOBAL", help="Country code to scope user entries (default GLOBAL)")
    parser.add_argument("--dry-run", action="store_true", help="Print merge summary without writing")
    args = parser.parse_args()

    seed = _load_seed_payload(args.user_list)
    chain_records = seed.get("chains") if isinstance(seed.get("chains"), list) else []
    franchise_names = seed.get("franchises") if isinstance(seed.get("franchises"), list) else []

    summary: Dict[str, Any] = {
        "input_chain_records": len(chain_records),
        "input_franchise_names": len(franchise_names),
    }

    if chain_records:
        chain_result = merge_user_chain_records(
            chain_records,
            default_country_code=args.country,
            persist=not bool(args.dry_run),
        )
        summary["chain_records"] = chain_result.get("summary") if isinstance(chain_result, dict) else {}
    else:
        summary["chain_records"] = {"input_count": 0, "added_chains": 0, "merged_chains": 0, "skipped": 0}

    if franchise_names:
        name_result = merge_user_franchise_list(
            franchise_names,
            country_code=args.country,
            persist=not bool(args.dry_run),
        )
        summary["franchise_names"] = name_result.get("summary") if isinstance(name_result, dict) else {}
    else:
        summary["franchise_names"] = {"input_count": 0, "added_chains": 0, "updated_aliases": 0, "skipped": 0}

    print(
        json.dumps(
            {
                "status": "ok",
                "summary": summary,
                "dry_run": bool(args.dry_run),
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
