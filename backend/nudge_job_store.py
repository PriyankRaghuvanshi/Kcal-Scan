"""
Coach nudge batch job run store.
Keeps recent scheduler run history for monitoring and alerting.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

_LOCK = threading.Lock()
_MAX_RUNS = 500


def _normalize_space(v: Any) -> str:
    return " ".join(str(v or "").strip().split())


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _store_path() -> Path:
    override = _normalize_space(os.getenv("NUDGE_JOB_STORE_PATH", ""))
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "nudge_job_runs.json"


def _empty_store() -> Dict[str, Any]:
    return {"runs": []}


def _load_store() -> Dict[str, Any]:
    path = _store_path()
    if not path.exists():
        return _empty_store()
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and isinstance(data.get("runs"), list):
            return data
    except Exception:
        pass
    return _empty_store()


def _save_store(store: Dict[str, Any]) -> None:
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=True, indent=2, sort_keys=True)


def create_job_run(job_name: str, trigger: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    run_id = str(uuid.uuid4())
    rec = {
        "run_id": run_id,
        "job_name": _normalize_space(job_name) or "coach_nudges_batch",
        "trigger": _normalize_space(trigger) or "manual",
        "status": "running",
        "started_at": _now_iso(),
        "finished_at": None,
        "duration_ms": None,
        "payload": payload if isinstance(payload, dict) else {},
        "result": {},
        "error": "",
    }
    with _LOCK:
        store = _load_store()
        runs = list(store.get("runs") or [])
        runs.append(rec)
        if len(runs) > _MAX_RUNS:
            runs = runs[-_MAX_RUNS:]
        store["runs"] = runs
        _save_store(store)
    return dict(rec)


def update_job_run(
    run_id: str,
    *,
    status: str,
    result: Optional[Dict[str, Any]] = None,
    error: str = "",
) -> Optional[Dict[str, Any]]:
    with _LOCK:
        store = _load_store()
        runs = list(store.get("runs") or [])
        now = datetime.now(timezone.utc)
        for r in runs:
            if not isinstance(r, dict):
                continue
            if _normalize_space(r.get("run_id")) != _normalize_space(run_id):
                continue
            started_raw = str(r.get("started_at") or "")
            try:
                started_dt = datetime.fromisoformat(started_raw)
                if started_dt.tzinfo is None:
                    started_dt = started_dt.replace(tzinfo=timezone.utc)
            except Exception:
                started_dt = now
            r["status"] = _normalize_space(status) or "done"
            r["finished_at"] = now.isoformat()
            r["duration_ms"] = int(max(0.0, (now - started_dt).total_seconds() * 1000.0))
            r["result"] = result if isinstance(result, dict) else {}
            r["error"] = str(error or "")[:2000]
            store["runs"] = runs
            _save_store(store)
            return dict(r)
    return None


def list_recent_job_runs(job_name: str, limit: int = 30) -> List[Dict[str, Any]]:
    with _LOCK:
        store = _load_store()
    runs = store.get("runs") or []
    out: List[Dict[str, Any]] = []
    for r in reversed(runs):
        if not isinstance(r, dict):
            continue
        if _normalize_space(r.get("job_name")) != _normalize_space(job_name):
            continue
        out.append(dict(r))
        if len(out) >= max(1, min(200, limit)):
            break
    return out


def summarize_job_health(job_name: str, within_hours: float = 24.0) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=max(1.0, min(168.0, float(within_hours))))
    rows = list_recent_job_runs(job_name, limit=200)
    total = 0
    failed = 0
    running = 0
    last_success_at = ""
    last_failure_at = ""
    for r in rows:
        started_raw = str(r.get("started_at") or "")
        try:
            started_dt = datetime.fromisoformat(started_raw)
            if started_dt.tzinfo is None:
                started_dt = started_dt.replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if started_dt < cutoff:
            continue
        total += 1
        status = _normalize_space(r.get("status")).lower()
        if status == "running":
            running += 1
        elif status in {"error", "failed"}:
            failed += 1
            if not last_failure_at:
                last_failure_at = str(r.get("finished_at") or r.get("started_at") or "")
        elif status in {"done", "ok", "success"}:
            if not last_success_at:
                last_success_at = str(r.get("finished_at") or r.get("started_at") or "")
    return {
        "job_name": job_name,
        "window_hours": float(within_hours),
        "runs_in_window": total,
        "failed_in_window": failed,
        "running_now": running,
        "last_success_at": last_success_at,
        "last_failure_at": last_failure_at,
    }
