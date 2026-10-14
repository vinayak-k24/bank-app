"""FraudShield REST API: the contract agreed with the frontend (backend brief, Section 5).

Mounted at the contract paths (/metrics, /transactions, /cases, /rings) and mirrored under
/api/fs/* so it sits beside the existing FinGuard /api routes.
"""

from __future__ import annotations

import hmac
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import get_settings
from app.services import fraudshield as fs
from app.services import state


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    expected = get_settings().api_key
    if expected and not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(401, "Missing or invalid X-API-Key")


router = APIRouter(tags=["fraudshield"], dependencies=[Depends(require_api_key)])

DecisionValue = Literal["APPROVE", "STEP_UP", "HOLD"]
CaseStatus = Literal["OPEN", "APPROVED", "REJECTED", "ESCALATED"]


class DecisionBreakdown(BaseModel):
    APPROVE: int
    STEP_UP: int
    HOLD: int


class Metrics(BaseModel):
    transactions_scored: int
    held_count: int
    amount_held: float
    open_cases: int
    step_up_count: int
    decision_breakdown: DecisionBreakdown
    as_of: str


class Transaction(BaseModel):
    txn_id: str
    customer_id: str
    dest_id: str | None = None
    type: str
    amount: float
    country: str
    device_id: str | None = None
    velocity_1h: int | None = None
    fraud_prob: float | None = None
    anomaly_distance: float | None = None
    risk_score: float
    decision: DecisionValue
    case_id: str | None = None
    ts: str


class Case(BaseModel):
    case_id: str
    txn_id: str
    customer_id: str
    amount: float | None = None
    type: str | None = None
    country: str | None = None
    device_id: str | None = None
    dest_id: str | None = None
    risk_score: float
    status: CaseStatus
    opened_at: str | None = None
    ai_summary: dict[str, Any] | None = None
    analyst_decision: str | None = None
    analyst_note: str | None = None
    decided_at: str | None = None


class DecisionRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED", "ESCALATED"]
    note: str = Field(default="", max_length=2000)


class DecisionResponse(BaseModel):
    case_id: str
    status: CaseStatus
    decided_at: str


class RingNode(BaseModel):
    id: str
    kind: Literal["customer", "device", "account"]


class RingEdge(BaseModel):
    source: str
    target: str


class Rings(BaseModel):
    nodes: list[RingNode]
    edges: list[RingEdge]


class CaseChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _call(fn, *args):
    try:
        return fn(*args)
    except fs.CaseNotFound:
        raise HTTPException(404, "Case not found")
    except fs.CaseAlreadyDecided as exc:
        raise HTTPException(409, f"Case already decided: {exc}")
    except fs.DataSourceError:
        raise HTTPException(503, "FraudShield data source unavailable")


@router.get("/metrics", response_model=Metrics)
def metrics():
    return _call(fs.get_repo().metrics)


@router.get("/transactions", response_model=list[Transaction], response_model_exclude_none=True)
def transactions(limit: int = Query(default=50, ge=1, le=500)):
    return _call(fs.get_repo().transactions, limit)


@router.get("/cases", response_model=list[Case])
def cases(status: CaseStatus | None = None, limit: int = Query(default=100, ge=1, le=500)):
    return _call(fs.get_repo().cases, status, limit)


@router.get("/cases/{case_id}", response_model=Case)
def case_detail(case_id: str):
    return _call(fs.get_repo().case, case_id)


@router.post("/cases/{case_id}/decision", response_model=DecisionResponse)
def case_decision(case_id: str, body: DecisionRequest):
    result = _call(fs.get_repo().decide, case_id, body.decision, body.note)
    state.audit("analyst", f"FraudShield case {body.decision}", {"case_id": case_id, "note": body.note})
    return result


@router.get("/rings", response_model=Rings)
def rings():
    return _call(fs.get_repo().rings)


@router.post("/cases/{case_id}/chat")
def case_chat(case_id: str, body: CaseChatRequest):
    _call(fs.get_repo().case, case_id)
    raise HTTPException(501, "Case chat ships in Phase B (Gemini investigation agent)")
