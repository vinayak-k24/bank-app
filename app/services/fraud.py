"""Payments & scam guard (R1). Scores are deterministic; Gemini only explains."""

from __future__ import annotations

import datetime as dt
import random
import uuid
from typing import Any

from app.data import mock_data
from app.services import state
from app.services.ai import get_ai

HOLD_THRESHOLD = 0.75
WARN_THRESHOLD = 0.40

_rng = random.Random(7)


def score_payment(customer_id: str, recipient: str, amount_usd: float, new_device: bool) -> dict[str, Any]:
    """Behavioral risk score (Vertex AI tabular model stand-in)."""
    persona = mock_data.PERSONAS.get(customer_id, mock_data.PERSONAS["CUST-101"])
    weekly_avg = max(persona["avg_monthly_deposits_usd"] / 4.0, 1.0)
    velocity = round(amount_usd / weekly_avg, 2)
    new_payee = recipient not in persona["known_payees"]

    factors: list[dict[str, Any]] = [{"factor": "Baseline", "weight": 0.10}]
    if new_device:
        factors.append({"factor": "Unrecognized device", "weight": 0.30})
        factors.append({"factor": "Unusual location", "weight": 0.25})
    if velocity > 2.0:
        factors.append({"factor": f"Amount is {velocity}x weekly average", "weight": round(min(0.20, velocity * 0.04), 2)})
    if new_payee:
        factors.append({"factor": "First payment to this recipient", "weight": 0.10})
    if recipient in mock_data.SCAM_PAYEES:
        factors.append({"factor": mock_data.SCAM_PAYEES[recipient], "weight": 0.40})
    if persona["risk_tier"] == "Critical-AML":
        factors.append({"factor": "Sender is under AML investigation", "weight": 0.40})

    score = round(min(0.98, sum(f["weight"] for f in factors)), 2)
    return {"score": score, "velocity_ratio": velocity, "new_payee": new_payee, "factors": factors}


def _decision(score: float) -> str:
    if score >= HOLD_THRESHOLD:
        return "HELD_FOR_CONFIRMATION"
    if score >= WARN_THRESHOLD:
        return "APPROVED_WITH_WARNING"
    return "APPROVED"


def send_payment(customer_id: str, recipient: str, amount_usd: float, new_device: bool) -> dict[str, Any]:
    scored = score_payment(customer_id, recipient, amount_usd, new_device)
    decision = _decision(scored["score"])
    top = "; ".join(f["factor"].lower() for f in scored["factors"][1:]) or "normal behavior"

    if decision == "HELD_FOR_CONFIRMATION":
        fallback = (
            f"We paused this ${amount_usd:,.0f} payment to {recipient} for your safety: {top}. "
            "Your account is not frozen. Confirm it's you via OTP, or block it if you didn't make it."
        )
    elif decision == "APPROVED_WITH_WARNING":
        fallback = f"Payment sent, but note: {top}. Double-check the recipient's details."
    else:
        fallback = "Payment matches your usual behavior and was approved."

    explanation = get_ai().text(
        "You are a bank fraud assistant. In 2 short plain-English sentences, explain this payment decision "
        f"to the customer. Do not change the decision. Decision={decision}, amount=${amount_usd:,.2f}, "
        f"recipient={recipient}, risk={int(scored['score'] * 100)}%, factors={top}. "
        "If held, say the account is not frozen and they can confirm via OTP.",
        fallback,
    )

    event = {
        "tx_id": f"TX-{uuid.uuid4().hex[:6].upper()}",
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "customer_id": customer_id,
        "recipient": recipient,
        "amount_usd": round(amount_usd, 2),
        "new_device": new_device,
        "risk_score": scored["score"],
        "risk_pct": int(round(scored["score"] * 100)),
        "factors": scored["factors"],
        "velocity_ratio": scored["velocity_ratio"],
        "decision": decision,
        "status": "on_hold" if decision == "HELD_FOR_CONFIRMATION" else "completed",
        "explanation": explanation,
        "source": "user",
        "pubsub_topic": "transactions-stream",
    }
    state.add_feed_event(event)
    state.audit("system", "payment_scored", {"tx_id": event["tx_id"], "decision": decision, "score": scored["score"]})
    if decision == "HELD_FOR_CONFIRMATION":
        state.open_case("payment_hold", customer_id, f"${amount_usd:,.0f} to {recipient} held at {event['risk_pct']}% risk", event["tx_id"])
        persona = mock_data.PERSONAS[customer_id]
        state.add_exposure({
            "id": event["tx_id"], "entity": persona["name"], "ref": "#" + event["tx_id"], "division": "retail" if customer_id != "AML-303" else "treasury",
            "customer_id": customer_id, "risk_type": "Payment held", "risk_note": f"To {recipient}", "score_label": "Vertex AI risk",
            "score": scored["score"], "sla": "Awaiting customer OTP", "exposure_usd": round(amount_usd, 2), "rule": "FP-07",
            "progress": 50, "progress_label": "Paused, account not frozen", "severity": "critical", "page": "payments", "status": "open",
        })
    return event


def synthetic_tick(customer_id: str | None = None) -> dict[str, Any]:
    """Background low-risk traffic for the live stream (for the active persona if given)."""
    if customer_id not in mock_data.PERSONAS:
        customer_id = _rng.choice(["CUST-101", "SME-202"])
    persona = mock_data.PERSONAS[customer_id]
    recipient = _rng.choice(persona["known_payees"])
    amount = round(_rng.uniform(25, 1800), 2)
    scored = score_payment(customer_id, recipient, amount, new_device=False)
    event = {
        "tx_id": f"TX-{uuid.uuid4().hex[:6].upper()}",
        "ts": dt.datetime.now().isoformat(timespec="seconds"),
        "customer_id": customer_id,
        "recipient": recipient,
        "amount_usd": amount,
        "new_device": False,
        "risk_score": scored["score"],
        "risk_pct": int(round(scored["score"] * 100)),
        "factors": scored["factors"],
        "velocity_ratio": scored["velocity_ratio"],
        "decision": _decision(scored["score"]),
        "status": "completed",
        "explanation": "Matches usual behavior.",
        "source": "stream",
        "pubsub_topic": "transactions-stream",
    }
    state.add_feed_event(event)
    return event


def resolve_hold(tx_id: str, action: str) -> dict[str, Any] | None:
    """action: 'confirm' (customer verified via OTP/chat) or 'block'."""
    event = state.get_feed_event(tx_id)
    if event is None or event["status"] != "on_hold":
        return event
    if action == "confirm":
        updated = state.update_feed_event(tx_id, status="completed", decision="CONFIRMED_BY_CUSTOMER")
        state.resolve(None, 0.0, "", {"holds_confirmed_by_customer": 1})
        state.update_exposure(tx_id, status="cleared", progress=100, progress_label="Confirmed by customer via OTP")
        state.audit("customer", "payment_confirmed_otp", {"tx_id": tx_id})
    else:
        updated = state.update_feed_event(tx_id, status="blocked", decision="BLOCKED")
        state.resolve(None, event["amount_usd"], f"Blocked {tx_id}", {"fraud_blocked_count": 1, "fraud_blocked_usd": event["amount_usd"]},
                      exposure=(tx_id, "Blocked before settlement"))
        state.audit("customer", "payment_blocked", {"tx_id": tx_id})
    return updated


def scan_invoice(file_bytes: bytes | None = None, mime_type: str | None = None, filename: str | None = None) -> dict[str, Any]:
    """Multimodal scam scan. Mock returns the INV-992 findings; live Gemini reads the upload."""
    inv = mock_data.SCAM_INVOICE
    findings = [
        {
            "field": "Bank account",
            "found": f"…{inv['routing_account_last4']}",
            "expected": f"…{inv['historical_verified_account_last4']}",
            "severity": "critical",
            "note": "Account differs from the vendor's verified payment history",
        },
        {
            "field": "Sender domain",
            "found": inv["sender_domain"],
            "expected": inv["verified_domain"],
            "severity": "critical",
            "note": f"Look-alike domain registered {inv['domain_age_days']} days ago",
        },
        {
            "field": "Language",
            "found": inv["urgency_language"],
            "expected": "Standard payment terms",
            "severity": "warning",
            "note": "Pressure tactic typical of social-engineering scams",
        },
    ]
    fallback = {
        "filename": filename or inv["filename"],
        "verdict": "SCAM_LIKELY",
        "risk_pct": 94,
        "vendor": inv["vendor_name"],
        "claimed_vendor": inv["claimed_vendor"],
        "invoice_number": inv["invoice_number"],
        "amount_usd": inv["invoice_amount_usd"],
        "findings": findings,
        "summary": (
            f"This invoice imitates {inv['claimed_vendor']} but asks you to pay a new account (…{inv['routing_account_last4']}) "
            f"from a look-alike domain created {inv['domain_age_days']} days ago. Don't pay it - verify with the vendor using a known phone number."
        ),
    }
    result = fallback
    if file_bytes:
        known = {
            "verified_vendor": inv["claimed_vendor"],
            "verified_domain": inv["verified_domain"],
            "verified_account_last4": inv["historical_verified_account_last4"],
        }
        result = get_ai().json(
            "You are a bank scam analyst. Inspect this invoice or payment screenshot. Compare it with the customer's "
            f"verified vendor records {known}. Return JSON with keys: verdict (SCAM_LIKELY|SUSPICIOUS|LOOKS_LEGIT), "
            "risk_pct (0-100), vendor, invoice_number, amount_usd (number), findings (list of {field, found, expected, "
            "severity: critical|warning|info, note}), summary (2 plain-English sentences).",
            fallback,
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
        result.setdefault("filename", filename)
    state.audit("system", "invoice_scanned", {"filename": result.get("filename"), "verdict": result.get("verdict")})
    return result


def block_scam_invoice() -> bool:
    inv = mock_data.SCAM_INVOICE
    changed = state.resolve("REC-SCAM", inv["invoice_amount_usd"], "Gemini blocked invoice scam INV-992", {"fraud_blocked_count": 1, "fraud_blocked_usd": inv["invoice_amount_usd"]},
                            exposure=("INV-992", "Blocked; vendor alerted"))
    state.audit("officer", "scam_invoice_blocked", {"invoice": inv["invoice_number"]})
    return changed
