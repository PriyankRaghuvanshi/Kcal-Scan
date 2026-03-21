from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return int(default)


def _normalize_chain_key(v: Any) -> str:
    return _safe_text(v).lower().replace(" ", "_")


def _normalize_market(v: Any) -> str:
    out = _safe_text(v).upper()
    return out if out in {"AU", "IN", "US"} else ""


def _base_dir() -> Path:
    override = _safe_text(os.getenv("CHAIN_BASELINE_SNAPSHOT_DIR"))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_baselines"


def snapshot_file_path(chain_key: Any, market: Any, registry_version: Any) -> Path:
    ck = _normalize_chain_key(chain_key) or "unknown_chain"
    mk = _normalize_market(market) or "XX"
    ver = max(1, _safe_int(registry_version, 1))
    return _base_dir() / mk / f"{ck}__v{ver}.json"


def load_chain_baseline_snapshot(chain_key: Any, market: Any, registry_version: Any) -> Optional[Dict[str, Any]]:
    path = snapshot_file_path(chain_key, market, registry_version)
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    return raw


def write_chain_baseline_snapshot(
    chain_key: Any,
    market: Any,
    registry_version: Any,
    snapshot_payload: Dict[str, Any],
) -> Path:
    path = snapshot_file_path(chain_key, market, registry_version)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot_payload if isinstance(snapshot_payload, dict) else {}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path

