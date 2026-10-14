"""Insurance claims (R3.5): claim invoice vs ledger-verified payment, deterministic payout cap."""

from __future__ import annotations

from typing import Any

from app.data import mock_data
from app.services import rag, state
from app.services.ai import get_ai

VARIANCE_LIMIT_PCT = 10.0


def analyze(kind: str, file_bytes: bytes | None = None, mime_type: str | None = None, filename: str | None = None) -> dict[str, Any]:
    claim = mock_data.CLAIMS[kind]
    fields = dict(claim["fields"])
    signals = list(claim["tamper_signals"])
    if file_bytes:
        extracted = get_ai().json(
            "Extract fields from this insurance claim invoice. Return JSON with keys: claimant, incident, repair_vendor, "
            "invoice_number, claimed_amount_usd (number), invoice_date, ocr_confidence (0-1), tamper_signals (list of strings: "
            "edited totals, line items not summing, duplicate invoice numbers).",
            {**fields, "tamper_signals": signals},
            file_bytes=file_bytes,
            mime_type=mime_type,
        )
        signals = extracted.pop("tamper_signals", signals) or []
        fields.update(extracted)

    claimed = float(fields["claimed_amount_usd"])
    paid = float(claim["ledger_payment"]["amount_usd"])
    variance_pct = round((claimed - paid) / max(paid, 1.0) * 100.0, 1)
    mismatch = abs(variance_pct) > VARIANCE_LIMIT_PCT
    pol = claim["policy"]
    payout = round(max(0.0, min(paid, claimed, pol["limit_usd"]) - pol["deductible_usd"]), 2)

    risk = 6 + (min(60, int(abs(variance_pct))) if mismatch else 0) + (25 if signals else 0)
    risk = min(98, risk)
    policy = rag.get("CLM-POL-12")
    flagged = mismatch or bool(signals)
    verdict = "ROUTE_TO_ADJUSTER" if flagged else "AUTO_APPROVED"
    fallback = (
        f"The claim asks for ${claimed:,.0f}, but the ledger shows only ${paid:,.0f} paid to {claim['ledger_payment']['payee']} "
        f"({variance_pct:+.1f}%). {'The invoice also shows signs of editing or reuse. ' if signals else ''}"
        f"Per {policy['doc_id']}, route to an adjuster; the maximum supportable payout is ${payout:,.0f} after the deductible."
        if flagged
        else f"The claimed ${claimed:,.0f} matches the verified ${paid:,.0f} payment to {claim['ledger_payment']['payee']}. "
             f"Auto-approved payout of ${payout:,.0f} after the ${pol['deductible_usd']:,.0f} deductible."
    )
    summary = get_ai().text(
        "You are an insurance claims assistant. Summarize this claim check for an adjuster in 2 sentences. Do not change "
        f"the verdict or payout. verdict={verdict}, claimed=${claimed:,.2f}, verified_payment=${paid:,.2f}, variance={variance_pct}%, "
        f"signals={signals}, payout=${payout:,.2f}, policy={policy['doc_id']}: {policy['clause']}",
        fallback,
    )
    state.audit("system", "claim_analyzed", {"claim_id": claim["claim_id"], "verdict": verdict})
    return {
        "doc_type": "claim",
        "kind": kind,
        "claim_id": claim["claim_id"],
        "filename": filename or claim["filename"],
        "customer_id": claim["customer_id"],
        "processor_type": claim["processor_type"],
        "policy": pol,
        "extracted_fields": fields,
        "lines": claim["lines"],
        "tamper_signals": signals,
        "ledger_check": {
            "declared_label": "Claim says",
            "ledger_label": "Ledger payment",
            "declared_usd": claimed,
            "ledger_usd": paid,
            "unit": "",
            "variance_pct": variance_pct,
            "limit_pct": VARIANCE_LIMIT_PCT,
            "match": not mismatch,
            "source": f"BigQuery ledger ({claim['ledger_payment']['tx_id']} on {claim['ledger_payment']['date']})",
        },
        "risk_score": risk,
        "verdict": verdict,
        "next_action": "Route to Adjuster" if flagged else "Release Payout",
        "payout_usd": payout,
        "policy_citation": {k: policy[k] for k in ("doc_id", "title", "clause")},
        "summary": summary,
    }


def route_to_adjuster(kind: str = "claim_inflated") -> dict[str, Any]:
    claim = mock_data.CLAIMS[kind]
    result = analyze(kind)
    avoided = round(result["ledger_check"]["declared_usd"] - result["payout_usd"], 2)
    s = state.snapshot()
    already = s["claims"].get(claim["claim_id"]) == "adjuster"
    if not already:
        state.resolve(None, avoided, f"Claims AI stopped inflated claim {claim['claim_id']}", {"claims_pending": -1},
                      exposure=(claim["claim_id"], "Routed to adjuster; payout capped"))
        claims = s["claims"] | {claim["claim_id"]: "adjuster"}
        state.set_value("claims", claims)
        state.audit("officer", "claim_routed_to_adjuster", {"claim_id": claim["claim_id"], "avoided_usd": avoided})
    return {"claim_id": claim["claim_id"], "changed": not already, "avoided_usd": avoided, "payout_cap_usd": result["payout_usd"]}


def release_payout(kind: str = "claim_clean") -> dict[str, Any]:
    claim = mock_data.CLAIMS[kind]
    result = analyze(kind)
    if result["verdict"] != "AUTO_APPROVED":
        raise ValueError("Claim needs adjuster review")
    s = state.snapshot()
    already = s["claims"].get(claim["claim_id"]) == "paid"
    if not already:
        state.set_value("claims", s["claims"] | {claim["claim_id"]: "paid"})
        state.audit("system", "claim_payout_released", {"claim_id": claim["claim_id"], "payout_usd": result["payout_usd"]})
    return {"claim_id": claim["claim_id"], "changed": not already, "payout_usd": result["payout_usd"]}
