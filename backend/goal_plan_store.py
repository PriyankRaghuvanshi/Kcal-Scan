from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


GOAL_PLAN_STORE_VERSION = "v1"
_LOCK = threading.Lock()
_MAX_PLANS_PER_USER = 5


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _env_path() -> Path:
    override = _normalize_space(os.getenv("GOAL_PLAN_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "goal_plans.json"


def _empty_store() -> Dict[str, Any]:
    return {"version": GOAL_PLAN_STORE_VERSION, "plans": []}


def _load_store() -> Dict[str, Any]:
    path = _env_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data.setdefault("version", GOAL_PLAN_STORE_VERSION)
            data.setdefault("plans", [])
            if isinstance(data.get("plans"), list):
                return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _env_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def _user_plans(store: Dict[str, Any], user_id: str) -> List[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    plans = store.get("plans") if isinstance(store.get("plans"), list) else []
    return [p for p in plans if isinstance(p, dict) and _normalize_space(p.get("user_id")) == uid]


def create_goal_plan(user_id: str, plan_input: Dict[str, Any], starter_plan: Dict[str, Any]) -> Dict[str, Any]:
    uid = _normalize_space(user_id)
    if not uid:
        raise ValueError("user_id_required")

    base = plan_input if isinstance(plan_input, dict) else {}
    plan_id = str(base.get("plan_id") or uuid.uuid4())
    now = _now_iso()

    timeframe_weeks = int(base.get("timeframe_weeks") or 0) or None
    timeline_days = (timeframe_weeks * 7) if timeframe_weeks else None
    row: Dict[str, Any] = {
        "plan_id": plan_id,
        "user_id": uid,
        "status": str(base.get("status") or "active"),
        "created_at": str(base.get("created_at") or now),
        "updated_at": now,
        "goal_type": str(base.get("goal_type") or "").strip().lower() or "fat_loss",
        "goal_preset": str(base.get("goal_preset") or "").strip() or None,
        "pace_mode": str(base.get("pace_mode") or "").strip().lower() or "balanced",
        "timeframe_weeks": timeframe_weeks,
        "timeline_days": timeline_days,
        "target_date": str(base.get("target_date") or "") or None,
        "training_days_per_week": int(base.get("training_days_per_week") or 0) or None,
        "diet_preference": str(base.get("diet_preference") or "").strip().lower() or None,
        "current_weight": base.get("current_weight"),
        "target_weight": base.get("target_weight"),
        "kickoff_started_at": str(base.get("kickoff_started_at") or now),
        "starter_plan": starter_plan if isinstance(starter_plan, dict) else {},
    }

    with _LOCK:
        store = _load_store()
        plans = store.get("plans") if isinstance(store.get("plans"), list) else []
        store["plans"] = plans

        # Mark other active plans as paused to keep one primary plan.
        for p in plans:
            if not isinstance(p, dict):
                continue
            if _normalize_space(p.get("user_id")) == uid and str(p.get("status") or "").strip() == "active":
                p["status"] = "paused"

        plans.append(row)

        # Soft cap total plans per user.
        user_specific = [p for p in plans if _normalize_space(p.get("user_id")) == uid]
        if len(user_specific) > _MAX_PLANS_PER_USER:
            # Drop oldest non-active plans first.
            non_active = [p for p in user_specific if str(p.get("status") or "") != "active"]
            non_active_sorted = sorted(non_active, key=lambda p: str(p.get("created_at") or ""))
            to_drop_ids = {p.get("plan_id") for p in non_active_sorted[: max(0, len(user_specific) - _MAX_PLANS_PER_USER)]}
            if to_drop_ids:
                store["plans"] = [p for p in plans if p.get("plan_id") not in to_drop_ids]

        store["version"] = GOAL_PLAN_STORE_VERSION
        _save_store(store)

    return dict(row)


def get_active_goal_plan(user_id: str) -> Optional[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    if not uid:
        return None
    with _LOCK:
        store = _load_store()
    plans = _user_plans(store, uid)
    active = [p for p in plans if str(p.get("status") or "").strip() == "active"]
    if active:
        # Newest active plan wins.
        active.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
        return dict(active[0])
    if plans:
        plans.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
        return dict(plans[0])
    return None


def update_goal_plan_status(user_id: str, status: str) -> Optional[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    if not uid:
        return None
    new_status = str(status or "").strip()
    if not new_status:
        return None
    with _LOCK:
        store = _load_store()
        plans = store.get("plans") if isinstance(store.get("plans"), list) else []
        store["plans"] = plans
        user_plans = [p for p in plans if isinstance(p, dict) and _normalize_space(p.get("user_id")) == uid]
        updated: Optional[Dict[str, Any]] = None
        if new_status == "paused":
            for p in user_plans:
                if str(p.get("status") or "").strip() == "active":
                    p["status"] = "paused"
                    p["updated_at"] = _now_iso()
                    updated = dict(p)
                    break
        elif new_status == "active":
            user_plans_sorted = sorted(
                user_plans,
                key=lambda x: str(x.get("updated_at") or x.get("created_at") or ""),
                reverse=True,
            )
            for p in user_plans:
                p["status"] = "paused"
            if user_plans_sorted:
                target = user_plans_sorted[0]
                target["status"] = "active"
                target["updated_at"] = _now_iso()
                updated = dict(target)
        if updated:
            store["version"] = GOAL_PLAN_STORE_VERSION
            _save_store(store)
        return updated


def list_goal_plans_for_user(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    if not uid:
        return []
    with _LOCK:
        store = _load_store()
    plans = _user_plans(store, uid)
    plans.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
    max_items = max(1, min(int(limit or 5), 20))
    return [dict(p) for p in plans[:max_items]]


def clear_goal_plan_store_for_tests() -> None:
    """Test helper: only enabled when GOAL_PLAN_ALLOW_CLEAR=true."""
    allow = _normalize_space(os.getenv("GOAL_PLAN_ALLOW_CLEAR", "")).lower()
    if allow not in {"1", "true", "yes", "y", "on"}:
        return
    with _LOCK:
        _save_store(_empty_store())

