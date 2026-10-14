"""Loan & document desk (R3). Extraction -> ledger check -> deterministic decision."""

from __future__ import annotations

from typing import Any

from app.data import mock_data
from app.services import rag, state
from app.services.ai import get_ai

VARIANCE_LIMIT_PCT = 15.0
OFFER_LIMIT_USD = 45000.00
OFFER_APR_PCT = 6.45


def _extract(kind: str, file_bytes: bytes | None, mime_type: str | None, filename: str | None) -> dict[str, Any]:
    doc = mock_data.DOCUMENTS[kind]
    if not file_bytes:
        return doc
    # Live Document AI stand-in: Gemini reads the uploaded statement
    fields = get_ai().json(
        "Extract fields from this bank statement. Return JSON with keys: account_holder, account_number (masked), "
        "statement_period, avg_monthly_deposits_usd (number), ending_balance_usd (number), ocr_confidence (0-1), "
        "tamper_signals (list of strings describing edits, font or total inconsistencies).",
        {**doc["fields"], "tamper_signals": doc["tamper_signals"]},
        file_bytes=file_bytes,
        mime_type=mime_type,
    )
    signals = fields.pop("tamper_signals", doc["tamper_signals"]) or []
    return {**doc, "filename": filename or doc["filename"], "fields": {**doc["fields"], **fields}, "tamper_signals": signals, "lines": doc["lines"]}


def analyze(kind: str, customer_id: str | None = None, file_bytes: bytes | None = None,
            mime_type: str | None = None, filename: str | None = None) -> dict[str, Any]:
    if kind not in mock_data.DOCUMENTS:
        kind = "tampered" if filename and "tamper" in filename.lower() else "clean"
    doc = _extract(kind, file_bytes, mime_type, filename)
    customer_id = customer_id or doc["customer_id"]
    persona = mock_data.PERSONAS.get(doc["customer_id"], mock_data.PERSONAS[customer_id])

    declared = float(doc["fields"]["avg_monthly_deposits_usd"])
    ledger = float(persona["avg_monthly_deposits_usd"])
    variance_pct = round((declared - ledger) / max(ledger, 1.0) * 100.0, 1)
    mismatch = abs(variance_pct) > VARIANCE_LIMIT_PCT
    tampered = bool(doc["tamper_signals"])

    risk = 8
    if mismatch:
        risk += min(60, int(abs(variance_pct)))
    if tampered:
        risk += 25
    risk = min(98, risk)

    policy = rag.get("UW-POLICY-104")
    if mismatch or tampered:
        verdict = "MANUAL_STEP_UP_REQUIRED"
        next_action = "Request Tax/GST Proof"
        fallback = (
            f"The statement claims ${declared:,.0f}/mo in deposits, but verified ledger history shows ${ledger:,.0f}/mo "
            f"({variance_pct:+.1f}%). {'The summary row also shows signs of editing. ' if tampered else ''}"
            f"Per {policy['doc_id']}, auto-approval is paused until Tax/GST proof is provided."
        )
    else:
        verdict = "INSTANT_PRE_APPROVED"
        next_action = "Accept Offer"
        fallback = (
            f"Statement deposits (${declared:,.0f}/mo) match the verified ledger (${ledger:,.0f}/mo). "
            f"Instant pre-approval of ${OFFER_LIMIT_USD:,.0f} at {OFFER_APR_PCT}% APR."
        )

    summary = get_ai().text(
        "You are a loan underwriting assistant. Summarize this document check for a loan officer in 2 sentences. "
        f"Do not change the verdict. Verdict={verdict}, declared=${declared:,.2f}/mo, ledger=${ledger:,.2f}/mo, "
        f"variance={variance_pct}%, tamper_signals={doc['tamper_signals']}, policy={policy['doc_id']}: {policy['clause']}",
        fallback,
    )

    result = {
        "filename": doc["filename"],
        "kind": kind,
        "customer_id": doc["customer_id"],
        "processor_type": doc["processor_type"],
        "extracted_fields": doc["fields"],
        "lines": doc["lines"],
        "tamper_signals": doc["tamper_signals"],
        "ledger_check": {
            "declared_label": "PDF says",
            "ledger_label": "BigQuery ledger",
            "declared_usd": declared,
            "ledger_usd": ledger,
            "unit": "/mo",
            "declared_monthly_deposits_usd": declared,
            "ledger_monthly_deposits_usd": ledger,
            "variance_pct": variance_pct,
            "limit_pct": VARIANCE_LIMIT_PCT,
            "match": not mismatch,
            "source": "BigQuery ledger (90 days)",
        },
        "risk_score": risk,
        "verdict": verdict,
        "next_action": next_action,
        "policy_citation": {k: policy[k] for k in ("doc_id", "title", "clause")},
        "summary": summary,
        "offer": None if verdict != "INSTANT_PRE_APPROVED" else {"limit_usd": OFFER_LIMIT_USD, "apr_pct": OFFER_APR_PCT, "term_months": 24},
    }
    state.audit("system", "document_analyzed", {"filename": doc["filename"], "verdict": verdict, "variance_pct": variance_pct})
    if verdict == "MANUAL_STEP_UP_REQUIRED":
        state.open_case("document_mismatch", doc["customer_id"], f"{doc['filename']}: deposits {variance_pct:+.1f}% vs ledger", doc["filename"])
    return result


def quote(amount_usd: float, apr_pct: float, term_months: int) -> dict[str, Any]:
    term_months = max(12, min(36, int(term_months)))
    r = apr_pct / 100.0 / 12.0
    payment = amount_usd / term_months if r == 0 else amount_usd * r / (1 - (1 + r) ** -term_months)
    total = payment * term_months
    return {
        "amount_usd": round(amount_usd, 2),
        "apr_pct": apr_pct,
        "term_months": term_months,
        "monthly_payment_usd": round(payment, 2),
        "total_interest_usd": round(total - amount_usd, 2),
    }


def pause_loan() -> bool:
    changed = state.resolve("REC-LOAN", OFFER_LIMIT_USD, "Document AI caught Apex income mismatch", {"loans_pending": -1},
                            exposure=("LN-4092", "Paused; GST proof requested"))
    state.set_value("loan", {"customer_id": "SME-202", "status": "paused_awaiting_gst_proof"})
    state.audit("officer", "loan_paused_request_gst", {"customer_id": "SME-202"})
    return changed
