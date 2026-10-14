"""FinGuard 360 FastAPI app. Run: uvicorn app.main:app --reload --port 8080"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.data import mock_data
from app.services import aml, claims, coach, command, fraud, state, underwriting
from app.services.ai import get_ai

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
ALLOWED_UPLOAD_TYPES = {"application/pdf", "image/png", "image/jpeg", "image/webp"}

app = FastAPI(title="FinGuard 360 API", version="3.0.0")


class PaymentRequest(BaseModel):
    customer_id: str = "CUST-101"
    recipient: str = Field(min_length=1, max_length=80)
    amount_usd: float = Field(gt=0, le=10_000_000)
    new_device: bool = False


class HoldAction(BaseModel):
    action: str = Field(pattern="^(confirm|block)$")


class QuoteRequest(BaseModel):
    amount_usd: float = Field(gt=0, le=1_000_000)
    apr_pct: float = Field(ge=0, le=60)
    term_months: int = Field(ge=12, le=36)


class SarSubmit(BaseModel):
    text: str = Field(min_length=1, max_length=50_000)
    officer: str = Field(default="Alex", max_length=80)


class EligibilityRequest(BaseModel):
    customer_id: str
    product_id: str
    delay_days: int = Field(default=0, ge=0, le=20)
    extra_expense_usd: float = Field(default=0, ge=0, le=100_000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    page: str = "command"
    persona_id: str = "CUST-101"
    history: list[dict[str, str]] = Field(default_factory=list, max_length=20)


async def _read_upload(file: UploadFile | None) -> tuple[bytes | None, str | None, str | None]:
    if file is None or not file.filename:
        return None, None, None
    if file.content_type not in ALLOWED_UPLOAD_TYPES:
        raise HTTPException(415, "Upload a PDF, PNG, JPEG or WebP file")
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File too large (max 10 MB)")
    return data, file.content_type, Path(file.filename).name


def _require_persona(customer_id: str) -> None:
    if customer_id not in mock_data.PERSONAS:
        raise HTTPException(404, f"Unknown persona {customer_id}")


# --- Shell & state ---------------------------------------------------------

@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ONLINE", "ai_mode": get_ai().mode}


@app.get("/api/personas")
def personas() -> list[dict[str, Any]]:
    customers = [
        {k: p[k] for k in ("customer_id", "name", "short", "segment", "risk_tier", "kyc_status", "default_document")}
        | {"scenario": mock_data.SCENARIOS[p["customer_id"]], "has_wallet": p["wallet"] is not None}
        for p in mock_data.PERSONAS.values()
    ]
    return [mock_data.GLOBAL_VIEW | {"has_wallet": False}] + customers


@app.get("/api/dashboard")
def get_dashboard(persona_id: str | None = None) -> dict[str, Any]:
    return command.dashboard(persona_id)


@app.get("/api/search")
def search(q: str = "") -> list[dict[str, Any]]:
    return command.search(q[:80])


@app.get("/api/state")
def get_state() -> dict[str, Any]:
    s = state.snapshot()
    s["ai_mode"] = get_ai().mode
    return s


@app.post("/api/state/reset")
def reset_state() -> dict[str, Any]:
    state.reset()
    return state.snapshot()


# --- Page 1: Command Center ------------------------------------------------

@app.get("/api/command/briefing")
def get_briefing(persona_id: str | None = None) -> dict[str, Any]:
    return command.briefing(persona_id)


@app.post("/api/command/actions/{rec_id}/execute")
def execute_action(rec_id: str) -> dict[str, Any]:
    try:
        return command.execute_recommendation(rec_id)
    except KeyError:
        raise HTTPException(404, "Unknown action")


# --- Page 2: Payments & Scam Guard -----------------------------------------

@app.post("/api/payments")
def send_payment(req: PaymentRequest) -> dict[str, Any]:
    _require_persona(req.customer_id)
    return fraud.send_payment(req.customer_id, req.recipient.strip(), req.amount_usd, req.new_device)


@app.post("/api/payments/tick")
def payment_tick(customer_id: str | None = None) -> dict[str, Any]:
    return fraud.synthetic_tick(customer_id)


@app.get("/api/payments/feed")
def payment_feed(limit: int = 15, customer_id: str | None = None) -> list[dict[str, Any]]:
    feed = state.snapshot()["feed"]
    if customer_id:
        feed = [e for e in feed if e["customer_id"] == customer_id]
    return feed[: max(1, min(limit, 50))]


@app.post("/api/payments/{tx_id}/resolve")
def resolve_payment(tx_id: str, req: HoldAction) -> dict[str, Any]:
    result = fraud.resolve_hold(tx_id, req.action)
    if result is None:
        raise HTTPException(404, "Unknown transaction")
    return result


@app.post("/api/scam/scan")
async def scan_invoice(file: UploadFile | None = File(default=None)) -> dict[str, Any]:
    data, mime, name = await _read_upload(file)
    return fraud.scan_invoice(data, mime, name)


@app.post("/api/scam/block")
def block_scam() -> dict[str, Any]:
    return {"changed": fraud.block_scam_invoice(), "state": state.snapshot()}


# --- Page 3: Loan & Document Desk ------------------------------------------

@app.post("/api/documents/analyze")
async def analyze_document(kind: str = Form(default="clean"), customer_id: str | None = Form(default=None),
                           file: UploadFile | None = File(default=None)) -> dict[str, Any]:
    data, mime, name = await _read_upload(file)
    if kind in mock_data.CLAIMS or (kind == "auto" and name and "claim" in name.lower()):
        if kind not in mock_data.CLAIMS:
            kind = "claim_inflated" if any(w in name.lower() for w in ("inflat", "tamper", "fake")) else "claim_clean"
        return claims.analyze(kind, data, mime, name)
    return underwriting.analyze(kind, customer_id, data, mime, name)


@app.post("/api/claims/{kind}/route")
def claim_route(kind: str) -> dict[str, Any]:
    if kind not in mock_data.CLAIMS:
        raise HTTPException(404, "Unknown claim")
    return claims.route_to_adjuster(kind) | {"state": state.snapshot()}


@app.post("/api/claims/{kind}/payout")
def claim_payout(kind: str) -> dict[str, Any]:
    if kind not in mock_data.CLAIMS:
        raise HTTPException(404, "Unknown claim")
    try:
        return claims.release_payout(kind) | {"state": state.snapshot()}
    except ValueError as exc:
        raise HTTPException(409, str(exc))


@app.post("/api/loans/quote")
def loan_quote(req: QuoteRequest) -> dict[str, Any]:
    return underwriting.quote(req.amount_usd, req.apr_pct, req.term_months)


@app.post("/api/loans/request-proof")
def request_proof() -> dict[str, Any]:
    return {"changed": underwriting.pause_loan(), "state": state.snapshot()}


# --- Page 4: Compliance & AML Studio ---------------------------------------

@app.get("/api/aml/cases/{case_id}/trace")
def aml_trace(case_id: str) -> dict[str, Any]:
    if case_id != mock_data.AML_CASE["case_id"]:
        raise HTTPException(404, "Unknown case")
    return aml.trace(case_id)


@app.get("/api/aml/cases/{case_id}/sar/stream")
def aml_sar_stream(case_id: str) -> StreamingResponse:
    if case_id != mock_data.AML_CASE["case_id"]:
        raise HTTPException(404, "Unknown case")
    return StreamingResponse(aml.draft_sar_stream(case_id), media_type="text/plain; charset=utf-8")


@app.post("/api/aml/cases/{case_id}/sar/submit")
def aml_sar_submit(case_id: str, req: SarSubmit) -> dict[str, Any]:
    if case_id != mock_data.AML_CASE["case_id"]:
        raise HTTPException(404, "Unknown case")
    record = aml.submit_sar(case_id, req.text, req.officer)
    return record | {"state": state.snapshot()}


# --- Page 5: Personal Financial Coach --------------------------------------

@app.get("/api/coach/{customer_id}/forecast")
def coach_forecast(customer_id: str, delay_days: int = 0, extra_expense_usd: float = 0.0) -> dict[str, Any]:
    _require_persona(customer_id)
    return coach.forecast(customer_id, delay_days, extra_expense_usd)


@app.get("/api/coach/{customer_id}/products")
def coach_products(customer_id: str) -> list[dict[str, Any]]:
    _require_persona(customer_id)
    return coach.products(customer_id)


@app.post("/api/coach/eligibility")
def coach_eligibility(req: EligibilityRequest) -> dict[str, Any]:
    _require_persona(req.customer_id)
    if not any(p["product_id"] == req.product_id for p in mock_data.PRODUCTS):
        raise HTTPException(404, "Unknown product")
    return coach.eligibility(req.customer_id, req.product_id, req.delay_days, req.extra_expense_usd)


# --- Copilot ----------------------------------------------------------------

@app.get("/api/copilot/suggestions")
def copilot_suggestions(page: str = "command", persona_id: str = "CUST-101") -> list[str]:
    return command.suggestions(page, persona_id)


@app.post("/api/copilot/chat")
def copilot_chat(req: ChatRequest) -> dict[str, Any]:
    return command.chat(req.message, req.page, req.persona_id, req.history)


# --- Static UI --------------------------------------------------------------

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
