"""
YieldPilot case workflow API: cases, comments, status, memo export.
User-scoped via X-User-Id header or user_id query/body. Internal review only.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from yieldpilot_case_workflow import (
    add_comment,
    build_memo_payload,
    create_case,
    create_case_from_recommendation,
    delete_case,
    get_case,
    list_cases,
    list_comments,
    list_status_history,
    memo_as_csv,
    memo_as_json,
    memo_as_txt,
    set_status,
    update_case,
)

router = APIRouter(prefix="/cases", tags=["yieldpilot-cases"])


def _uid_input_text(v: Optional[str]) -> str:
    if v is None:
        return ""
    return str(v).strip()


def _require_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
    user_id: Optional[str] = None,
) -> str:
    h = _uid_input_text(x_user_id)
    q = _uid_input_text(user_id) if user_id is not None else ""
    if h and q and h != q:
        raise HTTPException(status_code=401, detail="Conflicting user ids in header and query.")
    uid = h or q
    if not uid:
        raise HTTPException(status_code=401, detail="Missing user id. Pass X-User-Id header or user_id in body/query.")
    return uid


# ---------- Request/response models ----------


class CreateCaseBody(BaseModel):
    model_config = ConfigDict(protected_namespaces=())  # allow field name model_score (not a BaseModel hook)

    symbol: str
    profile_id: Optional[str] = None
    contract_symbol: Optional[str] = None
    scenario_type: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
    rationale: Optional[str] = None
    status: str = "draft"
    blocked: bool = False
    blocked_reason: Optional[str] = None
    model_score: Optional[float] = None
    capital_required: Optional[float] = None
    expected_monthly_income: Optional[float] = None
    probability_otm: Optional[float] = None
    assignment_risk: Optional[float] = None
    downside_risk: Optional[float] = None
    trend_score: Optional[float] = None
    drawdown_risk_score: Optional[float] = None
    event_risk_score: Optional[float] = None
    quality_score: Optional[float] = None
    next_earnings_date: Optional[str] = None
    earnings_days_away: Optional[int] = None
    earnings_provider_used: Optional[str] = None
    portfolio_guardrail_status: Optional[str] = None
    portfolio_guardrail_reasons_json: Optional[Dict[str, Any]] = None
    recommendation_snapshot_json: Optional[Dict[str, Any]] = None
    replay_snapshot_json: Optional[Dict[str, Any]] = None
    analytics_snapshot_json: Optional[Dict[str, Any]] = None
    tags_json: Optional[List[str]] = None
    user_id: Optional[str] = None


class FromRecommendationBody(BaseModel):
    profile_id: Optional[str] = None
    recommendation: Dict[str, Any] = Field(default_factory=dict)
    title: Optional[str] = None
    rationale_seed: Optional[str] = None
    user_id: Optional[str] = None


class PatchCaseBody(BaseModel):
    title: Optional[str] = None
    summary: Optional[str] = None
    rationale: Optional[str] = None
    status: Optional[str] = None
    blocked: Optional[bool] = None
    blocked_reason: Optional[str] = None
    tags_json: Optional[List[str]] = None
    user_id: Optional[str] = None


class CommentBody(BaseModel):
    body: str = ""
    user_id: Optional[str] = None


class StatusBody(BaseModel):
    new_status: str
    note: Optional[str] = None
    user_id: Optional[str] = None


# ---------- Endpoints ----------


@router.post("", response_model=dict)
def post_case(
    body: CreateCaseBody,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, body.user_id)
    case = create_case(
        user_id=uid,
        symbol=body.symbol,
        profile_id=body.profile_id,
        contract_symbol=body.contract_symbol,
        scenario_type=body.scenario_type,
        title=body.title,
        summary=body.summary,
        rationale=body.rationale,
        status=body.status,
        blocked=body.blocked,
        blocked_reason=body.blocked_reason,
        model_score=body.model_score,
        capital_required=body.capital_required,
        expected_monthly_income=body.expected_monthly_income,
        probability_otm=body.probability_otm,
        assignment_risk=body.assignment_risk,
        downside_risk=body.downside_risk,
        trend_score=body.trend_score,
        drawdown_risk_score=body.drawdown_risk_score,
        event_risk_score=body.event_risk_score,
        quality_score=body.quality_score,
        next_earnings_date=body.next_earnings_date,
        earnings_days_away=body.earnings_days_away,
        earnings_provider_used=body.earnings_provider_used,
        portfolio_guardrail_status=body.portfolio_guardrail_status,
        portfolio_guardrail_reasons_json=body.portfolio_guardrail_reasons_json,
        recommendation_snapshot_json=body.recommendation_snapshot_json,
        replay_snapshot_json=body.replay_snapshot_json,
        analytics_snapshot_json=body.analytics_snapshot_json,
        tags_json=body.tags_json,
    )
    return {"ok": True, "case": case}


@router.post("/from-recommendation", response_model=dict)
def post_case_from_recommendation(
    body: FromRecommendationBody,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, body.user_id)
    case = create_case_from_recommendation(
        user_id=uid,
        profile_id=body.profile_id,
        recommendation_payload=body.recommendation,
        title=body.title,
        rationale_seed=body.rationale_seed,
    )
    return {"ok": True, "case": case}


@router.get("", response_model=dict)
def get_cases(
    symbol: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    profile_id: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    cases = list_cases(
        uid,
        symbol=symbol,
        status=status,
        profile_id=profile_id,
        date_from=date_from,
        date_to=date_to,
        tag=tag,
        limit=limit,
        offset=offset,
    )
    return {"ok": True, "cases": cases}


@router.get("/{case_id:int}", response_model=dict)
def get_case_by_id(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    case = get_case(uid, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True, "case": case}


@router.patch("/{case_id:int}", response_model=dict)
def patch_case(
    case_id: int,
    body: PatchCaseBody,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, (body.user_id if body else None) or user_id)
    updated = update_case(
        uid,
        case_id,
        title=body.title if body else None,
        summary=body.summary if body else None,
        rationale=body.rationale if body else None,
        status=body.status if body else None,
        blocked=body.blocked if body else None,
        blocked_reason=body.blocked_reason if body else None,
        tags_json=body.tags_json if body else None,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True, "case": updated}


@router.post("/{case_id:int}/comment", response_model=dict)
def post_comment(
    case_id: int,
    body: CommentBody,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, body.user_id if body else None)
    comment = add_comment(uid, case_id, body.body if body else "")
    if not comment:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True, "comment": comment}


@router.get("/{case_id:int}/comments", response_model=dict)
def get_case_comments(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    comments = list_comments(uid, case_id)
    return {"ok": True, "comments": comments}


@router.post("/{case_id:int}/status", response_model=dict)
def post_case_status(
    case_id: int,
    body: StatusBody,
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, body.user_id if body else None)
    updated = set_status(uid, case_id, body.new_status, note=body.note if body else None)
    if not updated:
        raise HTTPException(status_code=404, detail="Case not found or invalid status")
    return {"ok": True, "case": updated}


@router.get("/{case_id:int}/status-history", response_model=dict)
def get_case_status_history(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    events = list_status_history(uid, case_id)
    return {"ok": True, "status_history": events}


@router.delete("/{case_id:int}", response_model=dict)
def delete_case_by_id(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    ok = delete_case(uid, case_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"ok": True}


# ---------- Memo export ----------


@router.get("/{case_id:int}/memo.json")
def get_memo_json(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    out = memo_as_json(uid, case_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return PlainTextResponse(out, media_type="application/json")


@router.get("/{case_id:int}/memo.csv")
def get_memo_csv(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    out = memo_as_csv(uid, case_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return PlainTextResponse(out, media_type="text/csv")


@router.get("/{case_id:int}/memo.txt")
def get_memo_txt(
    case_id: int,
    user_id: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id"),
):
    uid = _require_user_id(x_user_id, user_id)
    out = memo_as_txt(uid, case_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return PlainTextResponse(out, media_type="text/plain")
