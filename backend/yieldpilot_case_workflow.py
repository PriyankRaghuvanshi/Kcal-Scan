"""
YieldPilot internal case workflow: cases, comments, status events, memo export.
SQLite-backed; user-scoped. For internal review and documentation only.
"""
from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Status values for case workflow
STATUS_DRAFT = "draft"
STATUS_UNDER_REVIEW = "under_review"
STATUS_APPROVED = "approved"
STATUS_REJECTED = "rejected"
STATUS_ARCHIVED = "archived"
CASE_STATUSES = {STATUS_DRAFT, STATUS_UNDER_REVIEW, STATUS_APPROVED, STATUS_REJECTED, STATUS_ARCHIVED}

# Default tags (manual)
DEFAULT_TAGS = [
    "income",
    "covered-call",
    "wheel",
    "high-event-risk",
    "review-needed",
    "approved",
]

_DB_LOCK = threading.Lock()


def _db_path() -> Path:
    override = os.getenv("YIELDPILOT_CASE_DB_PATH", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parent / "data" / "yieldpilot_cases.sqlite"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: Optional[sqlite3.Connection] = None) -> None:
    """Create case_records, case_comments, case_status_events if not present."""
    own = conn is None
    if own:
        conn = _get_conn()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS case_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                profile_id TEXT,
                symbol TEXT NOT NULL,
                contract_symbol TEXT,
                scenario_type TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                title TEXT,
                summary TEXT,
                rationale TEXT,
                blocked INTEGER NOT NULL DEFAULT 0,
                blocked_reason TEXT,
                model_score REAL,
                capital_required REAL,
                expected_monthly_income REAL,
                probability_otm REAL,
                assignment_risk REAL,
                downside_risk REAL,
                trend_score REAL,
                drawdown_risk_score REAL,
                event_risk_score REAL,
                quality_score REAL,
                next_earnings_date TEXT,
                earnings_days_away INTEGER,
                earnings_provider_used TEXT,
                portfolio_guardrail_status TEXT,
                portfolio_guardrail_reasons_json TEXT,
                recommendation_snapshot_json TEXT,
                replay_snapshot_json TEXT,
                analytics_snapshot_json TEXT,
                tags_json TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_case_records_user_id ON case_records(user_id);
            CREATE INDEX IF NOT EXISTS idx_case_records_status ON case_records(status);
            CREATE INDEX IF NOT EXISTS idx_case_records_symbol ON case_records(symbol);
            CREATE INDEX IF NOT EXISTS idx_case_records_profile_id ON case_records(profile_id);
            CREATE INDEX IF NOT EXISTS idx_case_records_created_at ON case_records(created_at);

            CREATE TABLE IF NOT EXISTS case_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                body TEXT NOT NULL,
                FOREIGN KEY (case_id) REFERENCES case_records(id)
            );
            CREATE INDEX IF NOT EXISTS idx_case_comments_case_id ON case_comments(case_id);

            CREATE TABLE IF NOT EXISTS case_status_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                case_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                old_status TEXT,
                new_status TEXT NOT NULL,
                note TEXT,
                FOREIGN KEY (case_id) REFERENCES case_records(id)
            );
            CREATE INDEX IF NOT EXISTS idx_case_status_events_case_id ON case_status_events(case_id);
        """)
        conn.commit()
    finally:
        if own:
            conn.close()


def _row_to_case_record(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if k == "blocked":
            out[k] = bool(v)
        elif k in ("portfolio_guardrail_reasons_json", "recommendation_snapshot_json",
                   "replay_snapshot_json", "analytics_snapshot_json", "tags_json") and v:
            try:
                out[k] = json.loads(v)
            except Exception:
                out[k] = v
        else:
            out[k] = v
    return out


def _ensure_user_scope(user_id: str, case: Dict[str, Any]) -> bool:
    return str((case.get("user_id") or "")) == str(user_id or "")


def create_case(
    user_id: str,
    symbol: str,
    *,
    profile_id: Optional[str] = None,
    contract_symbol: Optional[str] = None,
    scenario_type: Optional[str] = None,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    rationale: Optional[str] = None,
    status: str = STATUS_DRAFT,
    blocked: bool = False,
    blocked_reason: Optional[str] = None,
    model_score: Optional[float] = None,
    capital_required: Optional[float] = None,
    expected_monthly_income: Optional[float] = None,
    probability_otm: Optional[float] = None,
    assignment_risk: Optional[float] = None,
    downside_risk: Optional[float] = None,
    trend_score: Optional[float] = None,
    drawdown_risk_score: Optional[float] = None,
    event_risk_score: Optional[float] = None,
    quality_score: Optional[float] = None,
    next_earnings_date: Optional[str] = None,
    earnings_days_away: Optional[int] = None,
    earnings_provider_used: Optional[str] = None,
    portfolio_guardrail_status: Optional[str] = None,
    portfolio_guardrail_reasons_json: Optional[Dict[str, Any]] = None,
    recommendation_snapshot_json: Optional[Dict[str, Any]] = None,
    replay_snapshot_json: Optional[Dict[str, Any]] = None,
    analytics_snapshot_json: Optional[Dict[str, Any]] = None,
    tags_json: Optional[List[str]] = None,
) -> Dict[str, Any]:
    if status not in CASE_STATUSES:
        status = STATUS_DRAFT
    now = _now_iso()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            init_schema(conn)
            conn.execute(
                """
                INSERT INTO case_records (
                    user_id, profile_id, symbol, contract_symbol, scenario_type,
                    created_at, updated_at, status, title, summary, rationale,
                    blocked, blocked_reason, model_score, capital_required, expected_monthly_income,
                    probability_otm, assignment_risk, downside_risk, trend_score,
                    drawdown_risk_score, event_risk_score, quality_score,
                    next_earnings_date, earnings_days_away, earnings_provider_used,
                    portfolio_guardrail_status, portfolio_guardrail_reasons_json,
                    recommendation_snapshot_json, replay_snapshot_json, analytics_snapshot_json,
                    tags_json
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    user_id or "",
                    profile_id,
                    symbol or "",
                    contract_symbol,
                    scenario_type,
                    now,
                    now,
                    status,
                    title,
                    summary,
                    rationale,
                    1 if blocked else 0,
                    blocked_reason,
                    model_score,
                    capital_required,
                    expected_monthly_income,
                    probability_otm,
                    assignment_risk,
                    downside_risk,
                    trend_score,
                    drawdown_risk_score,
                    event_risk_score,
                    quality_score,
                    next_earnings_date,
                    earnings_days_away,
                    earnings_provider_used,
                    portfolio_guardrail_status,
                    json.dumps(portfolio_guardrail_reasons_json) if portfolio_guardrail_reasons_json is not None else None,
                    json.dumps(recommendation_snapshot_json) if recommendation_snapshot_json is not None else None,
                    json.dumps(replay_snapshot_json) if replay_snapshot_json is not None else None,
                    json.dumps(analytics_snapshot_json) if analytics_snapshot_json is not None else None,
                    json.dumps(tags_json) if tags_json is not None else None,
                ),
            )
            case_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute(
                "INSERT INTO case_status_events (case_id, user_id, created_at, old_status, new_status, note) VALUES (?, ?, ?, ?, ?, ?)",
                (case_id, user_id or "", now, None, status, "Initial status"),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM case_records WHERE id = ?", (case_id,)).fetchone()
            return _row_to_case_record(row)
        finally:
            conn.close()


def create_case_from_recommendation(
    user_id: str,
    profile_id: Optional[str],
    recommendation_payload: Dict[str, Any],
    *,
    title: Optional[str] = None,
    rationale_seed: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a case from a live recommendation snapshot. Stores frozen snapshot and derived fields."""
    rec = recommendation_payload or {}
    symbol = str(rec.get("symbol") or rec.get("underlying") or "").strip() or "UNKNOWN"
    contract_symbol = (rec.get("contract_symbol") or rec.get("contractSymbol") or "").strip() or None
    scenario_type = (rec.get("scenario_type") or rec.get("scenarioType") or "").strip() or None
    model_score = None
    if "model_score" in rec:
        model_score = rec["model_score"]
    elif "modelScore" in rec:
        model_score = rec["modelScore"]
    else:
        try:
            model_score = float(rec.get("score") or rec.get("score_100") or 0)
        except (TypeError, ValueError):
            pass
    capital_required = rec.get("capital_required") or rec.get("capitalRequired")
    expected_monthly_income = rec.get("expected_monthly_income") or rec.get("expectedMonthlyIncome")
    probability_otm = rec.get("probability_otm") or rec.get("probabilityOtm")
    assignment_risk = rec.get("assignment_risk") or rec.get("assignmentRisk")
    downside_risk = rec.get("downside_risk") or rec.get("downsideRisk")
    trend_score = rec.get("trend_score") or rec.get("trendScore")
    drawdown_risk_score = rec.get("drawdown_risk_score") or rec.get("drawdownRiskScore")
    event_risk_score = rec.get("event_risk_score") or rec.get("eventRiskScore")
    quality_score = rec.get("quality_score") or rec.get("qualityScore")
    next_earnings_date = rec.get("next_earnings_date") or rec.get("nextEarningsDate")
    earnings_days_away = rec.get("earnings_days_away") or rec.get("earningsDaysAway")
    earnings_provider_used = rec.get("earnings_provider_used") or rec.get("earningsProviderUsed")
    guardrail = rec.get("portfolio_guardrail_status") or rec.get("portfolioGuardrailStatus")
    guardrail_reasons = rec.get("portfolio_guardrail_reasons") or rec.get("portfolioGuardrailReasons")
    if isinstance(guardrail_reasons, list):
        guardrail_reasons = {"reasons": guardrail_reasons}
    elif not isinstance(guardrail_reasons, dict):
        guardrail_reasons = None
    case_title = title or f"{symbol} – {scenario_type or 'scenario'}"
    return create_case(
        user_id=user_id,
        symbol=symbol,
        profile_id=profile_id,
        contract_symbol=contract_symbol,
        scenario_type=scenario_type,
        title=case_title,
        rationale=rationale_seed,
        model_score=model_score,
        capital_required=capital_required,
        expected_monthly_income=expected_monthly_income,
        probability_otm=probability_otm,
        assignment_risk=assignment_risk,
        downside_risk=downside_risk,
        trend_score=trend_score,
        drawdown_risk_score=drawdown_risk_score,
        event_risk_score=event_risk_score,
        quality_score=quality_score,
        next_earnings_date=next_earnings_date,
        earnings_days_away=earnings_days_away,
        earnings_provider_used=earnings_provider_used,
        portfolio_guardrail_status=guardrail,
        portfolio_guardrail_reasons_json=guardrail_reasons,
        recommendation_snapshot_json=rec,
        status=STATUS_DRAFT,
    )


def list_cases(
    user_id: str,
    *,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    profile_id: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    tag: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_conn()
        try:
            init_schema(conn)
            sql = "SELECT * FROM case_records WHERE user_id = ?"
            params: List[Any] = [user_id or ""]
            if symbol:
                sql += " AND symbol = ?"
                params.append(symbol)
            if status:
                sql += " AND status = ?"
                params.append(status)
            if profile_id:
                sql += " AND profile_id = ?"
                params.append(profile_id)
            if date_from:
                sql += " AND created_at >= ?"
                params.append(date_from)
            if date_to:
                sql += " AND created_at <= ?"
                params.append(date_to)
            if tag:
                sql += " AND (tags_json IS NOT NULL AND tags_json LIKE ?)"
                params.append(f"%{tag}%")
            sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            rows = conn.execute(sql, params).fetchall()
            return [_row_to_case_record(r) for r in rows]
        finally:
            conn.close()


def get_case(user_id: str, case_id: int) -> Optional[Dict[str, Any]]:
    with _DB_LOCK:
        conn = _get_conn()
        try:
            init_schema(conn)
            row = conn.execute("SELECT * FROM case_records WHERE id = ? AND user_id = ?", (case_id, user_id or "")).fetchone()
            if row is None:
                return None
            return _row_to_case_record(row)
        finally:
            conn.close()


def update_case(
    user_id: str,
    case_id: int,
    *,
    title: Optional[str] = None,
    summary: Optional[str] = None,
    rationale: Optional[str] = None,
    status: Optional[str] = None,
    blocked: Optional[bool] = None,
    blocked_reason: Optional[str] = None,
    tags_json: Optional[List[str]] = None,
    **kwargs: Any,
) -> Optional[Dict[str, Any]]:
    case = get_case(user_id, case_id)
    if not case:
        return None
    if status is not None and status not in CASE_STATUSES:
        status = case.get("status")
    now = _now_iso()
    updates: List[Tuple[str, Any]] = [("updated_at", now)]
    if title is not None:
        updates.append(("title", title))
    if summary is not None:
        updates.append(("summary", summary))
    if rationale is not None:
        updates.append(("rationale", rationale))
    if status is not None:
        updates.append(("status", status))
    if blocked is not None:
        updates.append(("blocked", 1 if blocked else 0))
    if blocked_reason is not None:
        updates.append(("blocked_reason", blocked_reason))
    if tags_json is not None:
        updates.append(("tags_json", json.dumps(tags_json)))
    for k, v in kwargs.items():
        if k in (
            "profile_id", "contract_symbol", "scenario_type", "model_score",
            "capital_required", "expected_monthly_income", "probability_otm",
            "assignment_risk", "downside_risk", "trend_score", "drawdown_risk_score",
            "event_risk_score", "quality_score", "next_earnings_date", "earnings_days_away",
            "earnings_provider_used", "portfolio_guardrail_status", "portfolio_guardrail_reasons_json",
            "recommendation_snapshot_json", "replay_snapshot_json", "analytics_snapshot_json",
        ):
            if k in ("portfolio_guardrail_reasons_json", "recommendation_snapshot_json",
                     "replay_snapshot_json", "analytics_snapshot_json") and isinstance(v, dict):
                updates.append((k, json.dumps(v)))
            else:
                updates.append((k, v))
    if len(updates) <= 1:
        return case
    with _DB_LOCK:
        conn = _get_conn()
        try:
            set_clause = ", ".join(f"{k} = ?" for k, _ in updates)
            vals = [v for _, v in updates]
            conn.execute(
                f"UPDATE case_records SET {set_clause} WHERE id = ? AND user_id = ?",
                vals + [case_id, user_id or ""],
            )
            if status is not None and status != case.get("status"):
                conn.execute(
                    "INSERT INTO case_status_events (case_id, user_id, created_at, old_status, new_status, note) VALUES (?, ?, ?, ?, ?, ?)",
                    (case_id, user_id or "", now, case.get("status"), status, "Status change"),
                )
            conn.commit()
            return get_case(user_id, case_id)
        finally:
            conn.close()


def delete_case(user_id: str, case_id: int) -> bool:
    case = get_case(user_id, case_id)
    if not case:
        return False
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute("DELETE FROM case_status_events WHERE case_id = ?", (case_id,))
            conn.execute("DELETE FROM case_comments WHERE case_id = ?", (case_id,))
            conn.execute("DELETE FROM case_records WHERE id = ? AND user_id = ?", (case_id, user_id or ""))
            conn.commit()
            return True
        finally:
            conn.close()


def add_comment(user_id: str, case_id: int, body: str) -> Optional[Dict[str, Any]]:
    case = get_case(user_id, case_id)
    if not case:
        return None
    now = _now_iso()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            init_schema(conn)
            conn.execute(
                "INSERT INTO case_comments (case_id, user_id, created_at, body) VALUES (?, ?, ?, ?)",
                (case_id, user_id or "", now, body or ""),
            )
            cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            conn.execute("UPDATE case_records SET updated_at = ? WHERE id = ? AND user_id = ?", (now, case_id, user_id or ""))
            conn.commit()
            row = conn.execute("SELECT * FROM case_comments WHERE id = ?", (cid,)).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()


def list_comments(user_id: str, case_id: int) -> List[Dict[str, Any]]:
    case = get_case(user_id, case_id)
    if not case:
        return []
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM case_comments WHERE case_id = ? ORDER BY created_at ASC",
                (case_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def set_status(user_id: str, case_id: int, new_status: str, note: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Set case status and record status event with optional note."""
    if new_status not in CASE_STATUSES:
        return None
    case = get_case(user_id, case_id)
    if not case:
        return None
    old_status = case.get("status")
    if old_status == new_status:
        return case
    now = _now_iso()
    with _DB_LOCK:
        conn = _get_conn()
        try:
            conn.execute(
                "UPDATE case_records SET status = ?, updated_at = ? WHERE id = ? AND user_id = ?",
                (new_status, now, case_id, user_id or ""),
            )
            conn.execute(
                "INSERT INTO case_status_events (case_id, user_id, created_at, old_status, new_status, note) VALUES (?, ?, ?, ?, ?, ?)",
                (case_id, user_id or "", now, old_status, new_status, note or "Status change"),
            )
            conn.commit()
            return get_case(user_id, case_id)
        finally:
            conn.close()


def list_status_history(user_id: str, case_id: int) -> List[Dict[str, Any]]:
    case = get_case(user_id, case_id)
    if not case:
        return []
    with _DB_LOCK:
        conn = _get_conn()
        try:
            rows = conn.execute(
                "SELECT * FROM case_status_events WHERE case_id = ? ORDER BY created_at ASC",
                (case_id,),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()


def build_memo_payload(user_id: str, case_id: int) -> Optional[Dict[str, Any]]:
    """Build memo content for JSON/CSV/TXT export."""
    case = get_case(user_id, case_id)
    if not case:
        return None
    comments = list_comments(user_id, case_id)
    status_history = list_status_history(user_id, case_id)
    rec = case.get("recommendation_snapshot_json") or {}
    guardrail_reasons = case.get("portfolio_guardrail_reasons_json") or {}
    reasons_list = guardrail_reasons.get("reasons") if isinstance(guardrail_reasons, dict) else []
    return {
        "case_title": case.get("title") or "",
        "symbol": case.get("symbol") or "",
        "scenario_type": case.get("scenario_type") or "",
        "model_score": case.get("model_score"),
        "capital_required": case.get("capital_required"),
        "expected_monthly_income": case.get("expected_monthly_income"),
        "key_risks": {
            "assignment_risk": case.get("assignment_risk"),
            "downside_risk": case.get("downside_risk"),
            "event_risk_score": case.get("event_risk_score"),
            "drawdown_risk_score": case.get("drawdown_risk_score"),
        },
        "signal_summary": {
            "trend_score": case.get("trend_score"),
            "quality_score": case.get("quality_score"),
        },
        "earnings_summary": {
            "next_earnings_date": case.get("next_earnings_date"),
            "earnings_days_away": case.get("earnings_days_away"),
            "earnings_provider_used": case.get("earnings_provider_used"),
        },
        "guardrail_summary": {
            "portfolio_guardrail_status": case.get("portfolio_guardrail_status"),
            "reasons": reasons_list,
        },
        "rationale": case.get("rationale") or "",
        "comments_summary": [{"created_at": c.get("created_at"), "body": c.get("body")} for c in comments],
        "current_status": case.get("status") or "",
        "created_at": case.get("created_at"),
        "updated_at": case.get("updated_at"),
        "profile_id": case.get("profile_id"),
        "blocked": case.get("blocked"),
        "blocked_reason": case.get("blocked_reason"),
    }


def memo_as_json(user_id: str, case_id: int) -> Optional[str]:
    payload = build_memo_payload(user_id, case_id)
    if payload is None:
        return None
    return json.dumps(payload, indent=2, default=str)


def memo_as_csv(user_id: str, case_id: int) -> Optional[str]:
    payload = build_memo_payload(user_id, case_id)
    if payload is None:
        return None
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["field", "value"])
    for k, v in payload.items():
        if isinstance(v, (dict, list)):
            v = json.dumps(v)
        w.writerow([k, v])
    return buf.getvalue()


def memo_as_txt(user_id: str, case_id: int) -> Optional[str]:
    payload = build_memo_payload(user_id, case_id)
    if payload is None:
        return None
    lines = [
        f"Title: {payload.get('case_title', '')}",
        f"Symbol: {payload.get('symbol', '')}",
        f"Scenario type: {payload.get('scenario_type', '')}",
        f"Model score: {payload.get('model_score')}",
        f"Capital required: {payload.get('capital_required')}",
        f"Expected monthly income: {payload.get('expected_monthly_income')}",
        "",
        "Key risks:",
        json.dumps(payload.get("key_risks") or {}, indent=2),
        "",
        "Signal summary:",
        json.dumps(payload.get("signal_summary") or {}, indent=2),
        "",
        "Earnings summary:",
        json.dumps(payload.get("earnings_summary") or {}, indent=2),
        "",
        "Guardrail summary:",
        json.dumps(payload.get("guardrail_summary") or {}, indent=2),
        "",
        f"Rationale: {payload.get('rationale', '')}",
        "",
        "Comments:",
    ]
    for c in payload.get("comments_summary") or []:
        lines.append(f"  [{c.get('created_at', '')}] {c.get('body', '')}")
    lines.extend([
        "",
        f"Current status: {payload.get('current_status', '')}",
        f"Created: {payload.get('created_at', '')}",
        f"Updated: {payload.get('updated_at', '')}",
        f"Profile: {payload.get('profile_id', '') or 'N/A'}",
    ])
    return "\n".join(lines)
