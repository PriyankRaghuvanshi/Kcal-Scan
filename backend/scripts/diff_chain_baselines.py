#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))
os.chdir(BACKEND)

for _env in (BACKEND / ".env", BACKEND.parent / ".env"):
    if _env.exists():
        with _env.open() as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        break

from chain_baseline_runner import diff_chain_against_baseline, list_stable_registry_chains


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _parse_chain_specs(raw: str) -> List[Dict[str, Any]]:
    specs: List[Dict[str, Any]] = []
    for token in [x.strip() for x in str(raw or "").split(",") if x.strip()]:
        parts = token.split(":")
        if len(parts) < 2:
            continue
        chain_key = _safe_text(parts[0]).lower()
        market = _safe_text(parts[1]).upper()
        version = int(parts[2]) if len(parts) > 2 and str(parts[2]).isdigit() else 1
        if chain_key and market:
            specs.append({"chain_key": chain_key, "market": market, "registry_version": version})
    return specs


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff current chain outputs against locked baselines")
    parser.add_argument(
        "--chains",
        type=str,
        default="",
        help="Optional comma list chain_key:market[:version], e.g. mcdonalds:AU:1,chipotle:US:1",
    )
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    parser.add_argument("--fail-on-drift", action="store_true", help="Exit non-zero if any guardrail fails")
    args = parser.parse_args()

    targets = _parse_chain_specs(args.chains) if args.chains else list_stable_registry_chains()
    if not targets:
        print(json.dumps({"ok": False, "error": "no_targets"}))
        sys.exit(1)

    results = []
    for t in targets:
        results.append(
            diff_chain_against_baseline(
                chain_key=str(t.get("chain_key") or ""),
                market=str(t.get("market") or ""),
                registry_version=int(t.get("registry_version") or 1),
            )
        )

    failed = [r for r in results if not bool(r.get("ok"))]
    out = {
        "ok": not bool(failed),
        "chains_total": len(results),
        "chains_failed": len(failed),
        "results": results,
    }
    print(json.dumps(out, indent=2 if args.pretty else None))
    if args.fail_on_drift and failed:
        sys.exit(2)


if __name__ == "__main__":
    main()
