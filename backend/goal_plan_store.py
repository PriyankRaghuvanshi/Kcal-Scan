from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


GOAL_PLAN_STORE_VERSION = "v1"
_LOCK = threading.Lock()
_MAX_PLANS_PER_USER = 5
_TABLE = "goal_plans"

logger = logging.getLogger(__name__)

_PLAN_COLUMNS = [
    "plan_id",
    "user_id",
    "status",
    "created_at",
    "updated_at",
    "goal_type",
    "goal_preset",
    "pace_mode",
    "timeframe_weeks",
    "timeline_days",
    "target_date",
    "training_days_per_week",
    "diet_preference",
    "current_weight",
    "target_weight",
    "kickoff_started_at",
    "starter_plan",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _env_path() -> Path:
    override = _normalize_space(os.getenv("GOAL_PLAN_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "goal_plans.json"


def _supabase_available() -> bool:
    # Explicit file-store override (used by tests that set GOAL_PLAN_STORE_PATH) wins.
    if _normalize_space(os.getenv("GOAL_PLAN_STORE_PATH", "")):
        return False
    if _normalize_space(os.getenv("GOAL_PLAN_FORCE_FILE_STORE", "")).lower() in {"1", "true", "yes", "y", "on"}:
        return False
    url = _normalize_space(os.getenv("SUPABASE_URL", ""))
    key = _normalize_space(os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    return bool(url and key)


def _supabase_endpoint() -> str:
    base = _normalize_space(os.getenv("SUPABASE_URL", "")).rstrip("/")
    return f"{base}/rest/v1/{_TABLE}"


def _supabase_headers(prefer: Optional[str] = None) -> Dict[str, str]:
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer
    return headers


def _requests():
    try:
        import requests  # type: ignore
        return requests
    except ModuleNotFoundError:
        return None


def _row_for_supabase(row: Dict[str, Any]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for col in _PLAN_COLUMNS:
        if col in row:
            payload[col] = row[col]
    # starter_plan is jsonb; ensure dict
    sp = payload.get("starter_plan")
    if sp is None:
        payload["starter_plan"] = {}
    elif not isinstance(sp, (dict, list)):
        payload["starter_plan"] = {}
    return payload


def _supabase_select_user(uid: str) -> Optional[List[Dict[str, Any]]]:
    r = _requests()
    if r is None:
        return None
    try:
        resp = r.get(
            _supabase_endpoint(),
            headers=_supabase_headers(),
            params={
                "user_id": f"eq.{uid}",
                "select": ",".join(_PLAN_COLUMNS),
                "order": "updated_at.desc",
            },
            timeout=6,
        )
        if resp.status_code >= 400:
            logger.warning("goal_plans select failed: %s %s", resp.status_code, resp.text[:200])
            return None
        data = resp.json() if resp.text else []
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("goal_plans select error: %s", exc)
        return None


def _supabase_upsert(row: Dict[str, Any]) -> bool:
    r = _requests()
    if r is None:
        return False
    try:
        resp = r.post(
            _supabase_endpoint(),
            headers=_supabase_headers("resolution=merge-duplicates,return=minimal"),
            data=json.dumps(_row_for_supabase(row)),
            timeout=8,
        )
        if resp.status_code >= 400:
            logger.warning("goal_plans upsert failed: %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("goal_plans upsert error: %s", exc)
        return False


def _supabase_patch_status(uid: str, plan_id: str, status: str, updated_at: str) -> bool:
    r = _requests()
    if r is None:
        return False
    try:
        resp = r.patch(
            _supabase_endpoint(),
            headers=_supabase_headers("return=minimal"),
            params={
                "user_id": f"eq.{uid}",
                "plan_id": f"eq.{plan_id}",
            },
            data=json.dumps({"status": status, "updated_at": updated_at}),
            timeout=6,
        )
        if resp.status_code >= 400:
            logger.warning("goal_plans patch failed: %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("goal_plans patch error: %s", exc)
        return False


def _supabase_patch_pause_active(uid: str, updated_at: str) -> bool:
    r = _requests()
    if r is None:
        return False
    try:
        resp = r.patch(
            _supabase_endpoint(),
            headers=_supabase_headers("return=minimal"),
            params={
                "user_id": f"eq.{uid}",
                "status": "eq.active",
            },
            data=json.dumps({"status": "paused", "updated_at": updated_at}),
            timeout=6,
        )
        if resp.status_code >= 400:
            logger.warning("goal_plans pause-active failed: %s %s", resp.status_code, resp.text[:200])
            return False
        return True
    except Exception as exc:
        logger.warning("goal_plans pause-active error: %s", exc)
        return False


def _supabase_delete_plans(uid: str, plan_ids: List[str]) -> None:
    if not plan_ids:
        return
    r = _requests()
    if r is None:
        return
    try:
        in_clause = "in.(" + ",".join(plan_ids) + ")"
        r.delete(
            _supabase_endpoint(),
            headers=_supabase_headers("return=minimal"),
            params={"user_id": f"eq.{uid}", "plan_id": in_clause},
            timeout=6,
        )
    except Exception as exc:
        logger.warning("goal_plans delete error: %s", exc)


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

    if _supabase_available():
        # Pause any other active plans first so only one active plan per user.
        _supabase_patch_pause_active(uid, now)
        ok = _supabase_upsert(row)
        if ok:
            # Enforce soft cap in Supabase: drop oldest non-active plans beyond cap.
            existing = _supabase_select_user(uid) or []
            if len(existing) > _MAX_PLANS_PER_USER:
                non_active = [p for p in existing if str(p.get("status") or "") != "active"]
                non_active.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""))
                overflow = len(existing) - _MAX_PLANS_PER_USER
                to_drop = [str(p.get("plan_id")) for p in non_active[:overflow] if p.get("plan_id")]
                if to_drop:
                    _supabase_delete_plans(uid, to_drop)
            return dict(row)
        # Fall through to file store if Supabase write failed.

    with _LOCK:
        store = _load_store()
        plans = store.get("plans") if isinstance(store.get("plans"), list) else []
        store["plans"] = plans

        for p in plans:
            if not isinstance(p, dict):
                continue
            if _normalize_space(p.get("user_id")) == uid and str(p.get("status") or "").strip() == "active":
                p["status"] = "paused"

        plans.append(row)

        user_specific = [p for p in plans if _normalize_space(p.get("user_id")) == uid]
        if len(user_specific) > _MAX_PLANS_PER_USER:
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

    if _supabase_available():
        rows = _supabase_select_user(uid)
        if rows is not None:
            if rows:
                active = [p for p in rows if str(p.get("status") or "").strip() == "active"]
                if active:
                    active.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
                    return dict(active[0])
                rows.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
                return dict(rows[0])
            return None
        # None means transport error — fall through to file store.

    with _LOCK:
        store = _load_store()
    plans = _user_plans(store, uid)
    active = [p for p in plans if str(p.get("status") or "").strip() == "active"]
    if active:
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
    now = _now_iso()

    if _supabase_available():
        rows = _supabase_select_user(uid)
        if rows is not None:
            if not rows:
                return None
            if new_status == "paused":
                active = [p for p in rows if str(p.get("status") or "").strip() == "active"]
                if not active:
                    return None
                active.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
                target = active[0]
                ok = _supabase_patch_status(uid, str(target.get("plan_id") or ""), "paused", now)
                if ok:
                    target = dict(target)
                    target["status"] = "paused"
                    target["updated_at"] = now
                    return target
                return None
            if new_status == "active":
                rows.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
                target = rows[0]
                _supabase_patch_pause_active(uid, now)
                ok = _supabase_patch_status(uid, str(target.get("plan_id") or ""), "active", now)
                if ok:
                    target = dict(target)
                    target["status"] = "active"
                    target["updated_at"] = now
                    return target
                return None
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
                    p["updated_at"] = now
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
                target["updated_at"] = now
                updated = dict(target)
        if updated:
            store["version"] = GOAL_PLAN_STORE_VERSION
            _save_store(store)
        return updated


def list_goal_plans_for_user(user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    uid = _normalize_space(user_id)
    if not uid:
        return []
    max_items = max(1, min(int(limit or 5), 20))

    if _supabase_available():
        rows = _supabase_select_user(uid)
        if rows is not None:
            rows.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
            return [dict(p) for p in rows[:max_items]]

    with _LOCK:
        store = _load_store()
    plans = _user_plans(store, uid)
    plans.sort(key=lambda p: str(p.get("updated_at") or p.get("created_at") or ""), reverse=True)
    return [dict(p) for p in plans[:max_items]]


def clear_goal_plan_store_for_tests() -> None:
    """Test helper: only enabled when GOAL_PLAN_ALLOW_CLEAR=true."""
    allow = _normalize_space(os.getenv("GOAL_PLAN_ALLOW_CLEAR", "")).lower()
    if allow not in {"1", "true", "yes", "y", "on"}:
        return
    with _LOCK:
        _save_store(_empty_store())
