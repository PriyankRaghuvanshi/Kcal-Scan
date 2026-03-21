from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_CACHE: Optional[Dict[str, Any]] = None


def _default_registry_path() -> Path:
    override = str(os.getenv("CHAIN_ROLLOUT_REGISTRY_PATH") or "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "chain_rollout_registry.json"


def _safe_text(v: Any) -> str:
    return str(v or "").strip()


def _safe_bool(v: Any, default: bool = False) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    txt = _safe_text(v).lower()
    if txt in {"1", "true", "yes", "y", "on"}:
        return True
    if txt in {"0", "false", "no", "n", "off"}:
        return False
    return bool(default)


def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(round(float(v)))
    except Exception:
        return int(default)


def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _normalize_chain_key(v: Any) -> str:
    return _safe_text(v).lower().replace(" ", "_")


def _normalize_market(v: Any) -> str:
    out = _safe_text(v).upper()
    return out if out in {"AU", "IN", "US"} else ""


def _safe_features(raw: Any) -> Dict[str, bool]:
    src = raw if isinstance(raw, dict) else {}
    return {
        "ranking_enabled": _safe_bool(src.get("ranking_enabled"), True),
        "evidence_enabled": _safe_bool(src.get("evidence_enabled"), False),
        "assumptions_enabled": _safe_bool(src.get("assumptions_enabled"), False),
        "branch_confidence_enabled": _safe_bool(src.get("branch_confidence_enabled"), False),
        "verified_enabled": _safe_bool(src.get("verified_enabled"), False),
        "verified_shadow_mode": _safe_bool(src.get("verified_shadow_mode"), True),
    }


def _safe_rollout(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    canary = max(0, min(100, _safe_int(src.get("canary_percent"), 0)))
    allowlist_user_ids = [str(x).strip() for x in (src.get("allowlist_user_ids") or []) if str(x).strip()]
    allowlist_regions = [str(x).strip() for x in (src.get("allowlist_regions") or []) if str(x).strip()]
    return {
        "enabled": _safe_bool(src.get("enabled"), True),
        "canary_percent": canary,
        "allowlist_user_ids": allowlist_user_ids,
        "allowlist_regions": allowlist_regions,
    }


def _safe_chain_row(raw: Any) -> Dict[str, Any]:
    src = raw if isinstance(raw, dict) else {}
    chain_key = _normalize_chain_key(src.get("chain_key") or src.get("chain_id"))
    market = _normalize_market(src.get("market"))
    status = _safe_text(src.get("status") or "experimental").lower()
    if status not in {"stable", "expansion", "experimental"}:
        status = "experimental"
    fallback_mode = _safe_text(src.get("fallback_mode") or "balanced").lower()
    if fallback_mode not in {"strict", "balanced", "conservative"}:
        fallback_mode = "balanced"
    return {
        "chain_key": chain_key,
        "market": market,
        "display_name": _safe_text(src.get("display_name") or chain_key),
        "status": status,
        "registry_version": max(1, _safe_int(src.get("registry_version"), 1)),
        "active_config_version": _safe_text(src.get("active_config_version") or ""),
        "baseline_snapshot_id": _safe_text(src.get("baseline_snapshot_id") or ""),
        "fallback_mode": fallback_mode,
        "features": _safe_features(src.get("features")),
        "rollout": _safe_rollout(src.get("rollout")),
        "guardrails_profile_id": _safe_text(src.get("guardrails_profile_id") or ""),
        "last_validated_at": _safe_text(src.get("last_validated_at") or ""),
        "owner": _safe_text(src.get("owner") or ""),
        "risk_level": _safe_text(src.get("risk_level") or "medium").lower(),
        "notes": _safe_text(src.get("notes") or ""),
        "configured": bool(chain_key and market),
    }


def _default_registry() -> Dict[str, Any]:
    return {
        "version": "v1",
        "chains": [],
        "settings": {
            "registry_enabled": False,
            "enforce_for_stable_only": True,
            "verified_tag_release_enabled": False,
            "verified_tag_policy_version": "verified_v1",
            "verified_tag_canary_percent": 0,
            "verified_tag_shadow_mode": True,
            "verified_tag_allowlist_user_ids": [],
            "verified_tag_allowlist_regions": [],
            "verified_min_confidence": 0.80,
            "verified_max_source_age_days": 45,
        },
    }


def _load_registry_uncached() -> Dict[str, Any]:
    path = _default_registry_path()
    if not path.exists():
        return _default_registry()
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return _default_registry()
    out = _default_registry()
    if not isinstance(raw, dict):
        return out
    out["version"] = _safe_text(raw.get("version") or "v1")
    settings = raw.get("settings") if isinstance(raw.get("settings"), dict) else {}
    out["settings"] = {
        "registry_enabled": _safe_bool(settings.get("registry_enabled"), False),
        "enforce_for_stable_only": _safe_bool(settings.get("enforce_for_stable_only"), True),
        "verified_tag_release_enabled": _safe_bool(settings.get("verified_tag_release_enabled"), False),
        "verified_tag_policy_version": _safe_text(settings.get("verified_tag_policy_version") or "verified_v1"),
        "verified_tag_canary_percent": max(0, min(100, _safe_int(settings.get("verified_tag_canary_percent"), 0))),
        "verified_tag_shadow_mode": _safe_bool(settings.get("verified_tag_shadow_mode"), True),
        "verified_tag_allowlist_user_ids": [str(x).strip() for x in (settings.get("verified_tag_allowlist_user_ids") or []) if str(x).strip()],
        "verified_tag_allowlist_regions": [str(x).strip() for x in (settings.get("verified_tag_allowlist_regions") or []) if str(x).strip()],
        "verified_min_confidence": max(0.0, min(1.0, _safe_float(settings.get("verified_min_confidence"), 0.80))),
        "verified_max_source_age_days": max(1, _safe_int(settings.get("verified_max_source_age_days"), 45)),
    }
    out["chains"] = [_safe_chain_row(x) for x in (raw.get("chains") or []) if isinstance(x, dict)]
    return out


def load_chain_rollout_registry(force_reload: bool = False) -> Dict[str, Any]:
    global _CACHE
    with _LOCK:
        if _CACHE is None or force_reload:
            _CACHE = _load_registry_uncached()
        return dict(_CACHE)


def clear_chain_rollout_registry_cache() -> None:
    global _CACHE
    with _LOCK:
        _CACHE = None


def default_chain_runtime_config(chain_key: Any = "", market: Any = "") -> Dict[str, Any]:
    return {
        "chain_key": _normalize_chain_key(chain_key),
        "market": _normalize_market(market),
        "status": "unconfigured",
        "registry_version": 0,
        "active_config_version": "",
        "baseline_snapshot_id": "",
        "fallback_mode": "balanced",
        "features": {
            "ranking_enabled": True,
            "evidence_enabled": False,
            "assumptions_enabled": False,
            "branch_confidence_enabled": False,
            "verified_enabled": False,
            "verified_shadow_mode": True,
        },
        "rollout": {
            "enabled": False,
            "canary_percent": 0,
            "allowlist_user_ids": [],
            "allowlist_regions": [],
        },
        "guardrails_profile_id": "",
        "last_validated_at": "",
        "owner": "",
        "risk_level": "medium",
        "notes": "",
        "configured": False,
    }


def get_chain_runtime_config(chain_key: Any, market: Any) -> Dict[str, Any]:
    ck = _normalize_chain_key(chain_key)
    mk = _normalize_market(market)
    if not ck or not mk:
        return default_chain_runtime_config(ck, mk)

    registry = load_chain_rollout_registry(force_reload=False)
    settings = registry.get("settings") if isinstance(registry.get("settings"), dict) else {}
    enabled = _safe_bool(settings.get("registry_enabled"), False)
    if not enabled:
        return default_chain_runtime_config(ck, mk)

    rows: List[Dict[str, Any]] = registry.get("chains") if isinstance(registry.get("chains"), list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _normalize_chain_key(row.get("chain_key")) == ck and _normalize_market(row.get("market")) == mk:
            out = default_chain_runtime_config(ck, mk)
            out.update(row)
            out["configured"] = True
            return out
    return default_chain_runtime_config(ck, mk)

