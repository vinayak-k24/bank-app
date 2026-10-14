"""Command center briefing, recommended actions and context-aware copilot (R5)."""

from __future__ import annotations

import json
from typing import Any

from app.data import mock_data
from app.services import aml, fraud, rag, state, underwriting
from app.services.ai import get_ai

SUGGESTIONS: dict[str, list[str]] = {
    "command": ["What needs my attention first today?", "How much did AI save this month?", "Summarize open alerts"],
    "payments": ["Why was the $48,500 payment held?", "How do I spot an invoice scam?", "What does 'pause, don't freeze' mean?"],
    "documents": ["Why was Apex Mfg's bank statement flagged?", "Why was claim CL-7741 routed to an adjuster?", "What does UW-104 require?"],
    "compliance": ["Summarize RBI KYC Sec 24(a)", "Explain the money loop in #AM-89412", "What is FATF Red Flag 3.1?"],
    "coach": ["When will my balance dip?", "Is the invoice credit line worth it?", "How can I avoid overdraft fees?"],
}


PERSONA_SUGGESTIONS: dict[str, dict[str, list[str]]] = {
    "CUST-101": {
        "command": ["What is Aarav's risk today?"],
        "payments": ["Why was Aarav's $48,500 payment held?"],
        "documents": ["Is Aarav's statement genuine?"],
        "coach": ["When will Aarav's balance dip?"],
    },
    "SME-202": {
        "command": ["What is Apex Mfg's risk today?"],
        "payments": ["Why was the NetCorp payment held?"],
        "documents": ["Why was Apex Mfg's bank statement flagged?"],
        "coach": ["How do I cover Apex's payroll dip?"],
    },
    "AML-303": {
        "command": ["What is the status of case #AM-89412?"],
        "payments": ["Why was Shell Co. A's transfer held?"],
        "compliance": ["Explain the money loop in #AM-89412"],
    },
}


def suggestions(page: str, persona_id: str) -> list[str]:
    base = SUGGESTIONS.get(page, SUGGESTIONS["command"])
    extra = PERSONA_SUGGESTIONS.get(persona_id, {}).get(page, [])
    return list(dict.fromkeys(extra + base))[:4]


def briefing(persona_id: str | None = None) -> dict[str, Any]:
    s = state.snapshot()
    k = s["kpis"]
    open_recs = [r for r in s["recommendations"] if r["status"] == "open"]
    lines = [
        f"Good morning, Alex. We monitored {k['transactions_monitored']:,} transactions and blocked {k['fraud_blocked_count']} fraud attempts worth ${k['fraud_blocked_usd']:,.0f}.",
        f"There are {k['open_alerts']} open alerts, {k['loans_pending']} loans pending and {k['open_aml_cases']} open AML cases.",
    ]
    if open_recs:
        lines.append("Top priorities: " + "; ".join(r["title"] for r in open_recs) + ".")
    else:
        lines.append("All recommended actions are resolved. Great work.")
    lines.append(f"Projected AI savings stand at ${k['projected_savings_usd']:,.0f}.")
    scenario = mock_data.SCENARIOS.get(persona_id or "")
    if scenario:
        lines.append(f"In focus: {mock_data.PERSONAS[persona_id]['name']}. {scenario['story']}")
    fallback = " ".join(lines)
    text = get_ai().text(
        "You are a bank risk chief of staff. Write a 4-sentence morning briefing for officer Alex using only these facts: "
        f"kpis={k}, open_actions={[r['title'] for r in open_recs]}, focus_customer={scenario['story'] if scenario else 'none'}.",
        fallback,
    )
    return {"greeting": "Good Morning, Alex", "briefing": text}


def execute_recommendation(rec_id: str) -> dict[str, Any]:
    rec = state.recommendation(rec_id)
    if rec is None:
        raise KeyError(rec_id)
    if rec_id == "REC-SCAM":
        changed = fraud.block_scam_invoice()
    elif rec_id == "REC-LOAN":
        changed = underwriting.pause_loan()
    elif rec_id == "REC-GROWTH":
        g = mock_data.GROWTH_CAMPAIGN
        changed = state.resolve("REC-GROWTH", 0.0, "", {"growth_offers_sent": g["segment_size"], "growth_nii_usd": g["expected_nii_usd"]}, is_alert=False)
        state.audit("officer", "growth_offers_launched", {"segment_size": g["segment_size"]})
    else:
        sar = state.snapshot()["sar"]
        text = sar["draft"] or aml._fallback_sar(aml.trace("AM-89412"))
        changed = aml.submit_sar("AM-89412", text, "Alex")["changed"]
    return {"rec_id": rec_id, "changed": changed, "state": state.snapshot()}


BASE_HEALTH = {"retail": 97, "sme": 86, "insurance": 95, "treasury": 74}


def _health_tone(h: int) -> str:
    return "ok" if h >= 92 else "warn" if h >= 80 else "bad"


def dashboard(persona_id: str | None = None) -> dict[str, Any]:
    """Command Center panels. Exposure, alerts, health and impact are computed from live state."""
    s = state.snapshot()
    k = s["kpis"]
    exposures = s["exposures"]
    if persona_id and persona_id in mock_data.PERSONAS:
        mine = [e for e in exposures if e["customer_id"] == persona_id]
    else:
        mine = exposures
    open_items = [e for e in mine if e["status"] == "open"]
    ranked = sorted(open_items, key=lambda e: e["exposure_usd"], reverse=True)

    divisions = []
    for d in mock_data.DIVISIONS:
        items = [e for e in exposures if e["division"] == d["id"]]
        open_n = sum(1 for e in items if e["status"] == "open")
        resolved_n = sum(1 for e in items if e["status"] == "resolved")
        health = min(99, BASE_HEALTH[d["id"]] + 5 * resolved_n)
        divisions.append(d | {"health": health, "tone": _health_tone(health), "open_alerts": open_n,
                               "status": "Review required" if open_n else "Clear"})

    ai_mode = get_ai().mode
    services = [
        {"name": "Gemini 2.5 Pro & Flash", "tone": "ai", "mode": "live" if ai_mode != "mock" else "mock"},
        {"name": "Pub/Sub stream", "tone": "ok", "mode": "mock"},
        {"name": "BigQuery ledger", "tone": "ok", "mode": "mock"},
        {"name": "Vertex AI anomaly model", "tone": "ai", "mode": "mock"},
        {"name": "Document AI", "tone": "ok", "mode": "mock"},
        {"name": "Vertex AI Search (RBI/FATF)", "tone": "ai", "mode": "mock"},
        {"name": "AlloyDB + Cloud Run", "tone": "ok", "mode": "mock"},
    ]

    open_exposure = round(sum(e["exposure_usd"] for e in exposures if e["status"] == "open"), 2)
    blocked_live = sum(i["savings_usd"] for i in s["interventions"] if i.get("live"))
    impact = [
        {"label": "Exposure at risk", "value": open_exposure, "fmt": "usd", "tone": "bad", "note": "Open items in the register"},
        {"label": "Projected savings", "value": k["projected_savings_usd"], "fmt": "usd", "tone": "ai", "note": f"+${blocked_live:,.0f} from today's actions"},
        {"label": "Customer friction", "value": k["false_positive_rate_pct"], "fmt": "pct2", "tone": "ok", "note": "False-positive hold rate"},
        {"label": "Risk margin impact", "value": k["risk_margin_bps"], "fmt": "bps", "tone": "blue", "note": "Risk-adjusted NIM"},
        {"label": "Document STP", "value": k["doc_stp_rate_pct"], "fmt": "pct", "tone": "ok", "note": "Document & KYC straight-through"},
        {"label": "Growth NII", "value": k["growth_nii_usd"], "fmt": "usd", "tone": "ai", "note": f"{k['growth_offers_sent']} AI offers sent"},
    ]
    return {
        "services": services,
        "ai_mode": ai_mode,
        "ranked_alerts": ranked,
        "exposure_table": sorted(mine, key=lambda e: (e["status"] != "open", -e["exposure_usd"])),
        "exposure_total_usd": round(sum(e["exposure_usd"] for e in open_items), 2),
        "divisions": divisions,
        "analytics": mock_data.ANALYTICS,
        "analytics_note": "Sample portfolio data",
        "impact": impact,
        "interventions": s["interventions"],
    }


def search(q: str) -> list[dict[str, Any]]:
    q = q.strip().lower()
    if len(q) < 2:
        return []
    s = state.snapshot()
    hits: list[dict[str, Any]] = []
    for p in mock_data.PERSONAS.values():
        if q in p["name"].lower() or q in p["customer_id"].lower():
            hits.append({"type": "Customer", "title": p["name"], "sub": p["customer_id"], "persona": p["customer_id"], "page": "command"})
    for e in s["exposures"]:
        if q in e["ref"].lower() or q in e["entity"].lower() or q in e["risk_type"].lower():
            hits.append({"type": "Case", "title": f"{e['ref']} · {e['entity']}", "sub": e["risk_type"], "persona": e["customer_id"], "page": e["page"]})
    for t in s["feed"]:
        if q in t["tx_id"].lower() or q in t["recipient"].lower():
            hits.append({"type": "Transaction", "title": f"{t['tx_id']} · ${t['amount_usd']:,.0f}", "sub": t["recipient"], "persona": t["customer_id"], "page": "payments"})
    for p in mock_data.POLICIES:
        if q in p["doc_id"].lower() or q in p["title"].lower():
            hits.append({"type": "Policy", "title": p["doc_id"], "sub": p["title"], "persona": None, "page": "compliance" if p["category"] == "AML_REGULATION" else "documents"})
    if "sar" in q or "89412" in q:
        hits.append({"type": "SAR", "title": "SAR #AM-89412", "sub": s["sar"]["status"].replace("_", " "), "persona": "AML-303", "page": "compliance"})
    return hits[:12]


def _context(page: str, persona_id: str) -> dict[str, Any]:
    s = state.snapshot()
    persona = mock_data.PERSONAS.get(persona_id, mock_data.PERSONAS["CUST-101"])
    held = [e for e in s["feed"] if e["status"] == "on_hold" and e["customer_id"] == persona["customer_id"]][:3]
    return {
        "page": page,
        "persona": {k: persona[k] for k in ("customer_id", "name", "segment", "risk_tier")},
        "kpis": s["kpis"],
        "open_actions": [r["title"] for r in s["recommendations"] if r["status"] == "open"],
        "held_payments": [{k: e[k] for k in ("tx_id", "recipient", "amount_usd", "risk_pct", "explanation")} for e in held],
        "loan": s["loan"],
        "sar_status": s["sar"]["status"],
    }


def _mock_answer(message: str, page: str, ctx: dict[str, Any]) -> str:
    m = message.lower()
    k = ctx["kpis"]
    pid = ctx["persona"]["customer_id"]
    if "risk today" in m or "status of case" in m:
        p = ctx["persona"]
        return f"{p['name']} ({p['segment']}) is rated {p['risk_tier']}. {mock_data.SCENARIOS[pid]['story']}"
    if "statement" in m and pid == "CUST-101" and "apex" not in m:
        return "Yes. Aarav's statement shows $14,250/mo in deposits, which matches the verified BigQuery ledger exactly, and no tamper signals were found. He qualifies for the $45,000 instant pre-approval at 6.45% APR."
    if "48,500" in m or "held" in m:
        if ctx["held_payments"]:
            h = ctx["held_payments"][0]
            return f"{h['tx_id']} (${h['amount_usd']:,.0f} to {h['recipient']}) was held at {h['risk_pct']}% risk. {h['explanation']}"
        s = fraud.score_payment(pid, **mock_data.SCENARIOS[pid]["payment"])
        pay = mock_data.SCENARIOS[pid]["payment"]
        return f"A ${pay['amount_usd']:,.0f} payment to {pay['recipient']} scores {int(s['score'] * 100)}%: " + "; ".join(f["factor"] for f in s["factors"][1:]) + ". Anything at or above 75% is paused for confirmation, and the account stays open."
    if "claim" in m:
        return "Claim CL-7741 asks for $175,000, but BigQuery shows only $112,500 paid to Precision Tools Ltd (+55.6%), the invoice total was edited, and the invoice number was used on a 2025 claim. Per CLM-12 it goes to an adjuster with payout capped at $107,500, avoiding $67,500."
    if "apex" in m or "statement" in m or "flag" in m:
        return "Apex Mfg's statement claims $18,500/mo in deposits, but the verified ledger shows $12,400/mo (+49.2%). The summary row also has an edited text layer. UW-104 pauses auto-approval when the variance is over 15%, so we requested Tax/GST proof."
    if "uw-104" in m or "gst" in m:
        p = rag.get("UW-POLICY-104")
        return f"{p['title']}: {p['clause']}"
    if "24" in m or "rbi" in m:
        p = rag.get("RBI-KYC-24A")
        return f"{p['title']}: {p['clause']} In #AM-89412, $1.2M looped through 4 accounts in ~47 hours with no invoices, which meets all three criteria."
    if "fatf" in m or "3.1" in m:
        p = rag.get("FATF-REDFLAG-3.1")
        return f"{p['title']}: {p['clause']}"
    if "loop" in m or "am-89412" in m:
        return "Shell Co. A -> Transit Account B -> Global Traders C -> Holding Co. D -> back to Shell Co. A: four $300,000 transfers between Oct 11 and Oct 13 ($1.2M total, no supporting invoices)."
    if "scam" in m or "invoice" in m:
        return "Red flags: a changed bank account, a look-alike sender domain that was registered recently, and urgent payment pressure. Always verify a new account with the vendor using a known phone number."
    if "freeze" in m or "pause" in m:
        return "FinGuard pauses only the single risky payment and asks you to confirm via OTP or chat. Your account and cards keep working (policy FP-07)."
    if "dip" in m or "balance" in m or "overdraft" in m or "credit line" in m:
        fc = coach_forecast(ctx["persona"]["customer_id"])
        if not fc["available"]:
            return fc["reason"]
        d = fc["dip"]
        if not d["detected"]:
            return "No dip is forecast in the next 30 days."
        return f"Your balance is forecast to fall below ${fc['low_threshold_usd']:,.0f} on {d['first_low_date']} for {d['gap_days']} days (lowest ${d['lowest_balance_usd']:,.0f} on {d['lowest_date']}). The 6.45% Smart Invoice Credit Line can bridge it with no overdraft fees."
    if "saving" in m or "save" in m:
        return f"Projected AI savings are ${k['projected_savings_usd']:,.0f}, including ${k['fraud_blocked_usd']:,.0f} in blocked fraud."
    if "attention" in m or "alert" in m or "first" in m:
        acts = ctx["open_actions"]
        return f"{k['open_alerts']} open alerts. Highest priority: " + ("; ".join(acts) if acts else "nothing outstanding, all actions resolved") + "."
    return f"I'm in demo mode on the {page} page. Try one of the suggested questions, or ask about held payments, the Apex statement, case #AM-89412, or the cash-flow forecast."


def coach_forecast(customer_id: str) -> dict[str, Any]:
    from app.services import coach

    return coach.forecast(customer_id)


def chat(message: str, page: str, persona_id: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    ctx = _context(page, persona_id)
    fallback = _mock_answer(message, page, ctx)
    convo = "\n".join(f"{h.get('role', 'user')}: {h.get('content', '')}" for h in (history or [])[-6:])
    reply = get_ai().text(
        "You are FinGuard Copilot, a banking risk assistant. Answer in at most 4 sentences, using only the context "
        "and these policies. Never approve, block or move money yourself; point to the right page and action.\n"
        f"Policies: {json.dumps([{k: p[k] for k in ('doc_id', 'clause')} for p in mock_data.POLICIES])}\n"
        f"Context: {json.dumps(ctx, default=str)}\nConversation:\n{convo}\nuser: {message}",
        fallback,
    )
    return {"reply": reply, "suggestions": SUGGESTIONS.get(page, SUGGESTIONS["command"])}
