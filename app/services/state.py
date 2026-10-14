"""In-memory shared state (single source of truth for KPIs, alerts and cases).

On Google Cloud this maps to Cloud SQL (operational) + BigQuery (history).
"""

from __future__ import annotations

import copy
import datetime as dt
import threading
import uuid
from typing import Any

from app.data import mock_data

_lock = threading.RLock()


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def _initial() -> dict[str, Any]:
    last = len(mock_data.SAVINGS_SERIES) - 1
    return {
        "kpis": copy.deepcopy(mock_data.BASE_KPIS),
        "savings_series": copy.deepcopy(mock_data.SAVINGS_SERIES),
        # Labelled markers on the impact chart; new ones land on the latest month
        "interventions": [dict(i, ts=None, live=False) for i in copy.deepcopy(mock_data.HISTORIC_INTERVENTIONS)],
        "latest_index": last,
        "recommendations": [
            {
                "id": "REC-AML",
                "page": "compliance",
                "severity": "critical",
                "kind": "risk",
                "title": "Freeze 4-account AML ring & file SAR (#AM-89412)",
                "detail": "4 shell accounts moved $1.2M in a closed loop within 72h.",
                "savings_usd": 1200000.00,
                "meta": [["Loss avoidance", "$1,200,000"], ["Affected", "4 shell accounts"], ["Effort", "Low · 2 min"]],
                "grounding": "RBI KYC Sec 24(a) & FATF 3.1",
                "status": "open",
            },
            {
                "id": "REC-LOAN",
                "page": "documents",
                "severity": "warning",
                "kind": "risk",
                "title": "Hold Apex Mfg loan for income proof (#LN-4092)",
                "detail": "PDF shows $18,500/mo vs $12,400/mo verified ledger (+49.2%).",
                "savings_usd": 45000.00,
                "meta": [["Default avoided", "$45,000"], ["Discrepancy", "$18.5K vs $12.4K"], ["Effort", "Auto · 30 sec"]],
                "grounding": "UW-104 · Document AI vs BigQuery ledger",
                "status": "open",
            },
            {
                "id": "REC-SCAM",
                "page": "payments",
                "severity": "critical",
                "kind": "risk",
                "title": "Block invoice scam targeting Apex Manufacturing",
                "detail": "Invoice INV-992 routes $14,250 to a new account (…8841) from a 4-day-old domain.",
                "savings_usd": 14250.00,
                "meta": [["Customer exposure", "$14,250"], ["Signals", "Spoofed account + domain"], ["Effort", "1 click"]],
                "grounding": "FP-07 · Gemini multimodal scan",
                "status": "open",
            },
            {
                "id": "REC-GROWTH",
                "page": "coach",
                "severity": "growth",
                "kind": "growth",
                "title": f"Offer invoice credit to {mock_data.GROWTH_CAMPAIGN['segment_size']} cash-tight SMEs",
                "detail": "Vertex AI forecasts a 14-30 day cash gap for these customers; all pre-qualify for the 6.45% line.",
                "savings_usd": 0.0,
                "revenue_usd": mock_data.GROWTH_CAMPAIGN["expected_nii_usd"],
                "meta": [["Expected revenue", "+$410,000 NII"], ["Segment", "340 prime SMEs"], ["Effort", "1-click campaign"]],
                "grounding": "30-day cash-flow forecast · PROD-INV-FIN-01",
                "status": "open",
            },
        ],
        # Exposure register: drives the ranked alerts panel and the exposure table
        "exposures": [
            {"id": "AM-89412", "entity": "Shell Co. ring", "ref": "#AM-89412", "division": "treasury", "customer_id": "AML-303",
             "risk_type": "Circular layering", "risk_note": "Round-tripping in 72h", "score_label": "Vertex AI score", "score": 0.96,
             "sla": "< 45 min to settlement", "exposure_usd": 1200000.00, "rule": "RBI KYC 24(a) · FATF 3.1",
             "progress": 92, "progress_label": "SAR ready for sign-off", "severity": "critical", "page": "compliance", "status": "open"},
            {"id": "LN-4092", "entity": "Apex Manufacturing", "ref": "#LN-4092", "division": "sme", "customer_id": "SME-202",
             "risk_type": "Income mismatch", "risk_note": "PDF $18.5K vs ledger $12.4K", "score_label": "Tamper risk", "score": 0.94,
             "sla": "Disbursal in 4.5h", "exposure_usd": 45000.00, "rule": "UW-104",
             "progress": 68, "progress_label": "Document AI discrepancy hold", "severity": "warning", "page": "documents", "status": "open"},
            {"id": "CL-7741", "entity": "Apex Manufacturing", "ref": "#CL-7741", "division": "insurance", "customer_id": "SME-202",
             "risk_type": "Inflated claim", "risk_note": "Claim $175K vs paid $112.5K", "score_label": "Claim risk", "score": 0.89,
             "sla": "Payout due 17:00", "exposure_usd": 175000.00, "rule": "CLM-12",
             "progress": 55, "progress_label": "Invoice vs payment cross-check", "severity": "warning", "page": "documents", "status": "open"},
            {"id": "INV-992", "entity": "Apex Manufacturing", "ref": "#INV-992", "division": "retail", "customer_id": "SME-202",
             "risk_type": "Invoice scam (APP)", "risk_note": "Spoofed account + domain", "score_label": "Gemini scam score", "score": 0.94,
             "sla": "Real-time hold", "exposure_usd": 14250.00, "rule": "FP-07",
             "progress": 80, "progress_label": "Awaiting block decision", "severity": "critical", "page": "payments", "status": "open"},
            {"id": "LN-4108", "entity": "Aarav Sharma", "ref": "#LN-4108", "division": "retail", "customer_id": "CUST-101",
             "risk_type": "Pre-approval", "risk_note": "Statement matches ledger", "score_label": "Verification", "score": 0.998,
             "sla": "Auto-cleared", "exposure_usd": 45000.00, "rule": "UW-104",
             "progress": 100, "progress_label": "Verified via Document AI + BigQuery", "severity": "ok", "page": "documents", "status": "cleared"},
        ],
        "feed": [],  # payment events (Pub/Sub topic in GCP)
        "cases": [],  # back-office handoffs (R5.2)
        "audit": [],
        "sar": {"case_id": "AM-89412", "draft": "", "status": "not_started"},
        "loan": {"customer_id": "SME-202", "status": "pending_review"},
        "claims": {},
    }


_state: dict[str, Any] = _initial()


def snapshot() -> dict[str, Any]:
    with _lock:
        return copy.deepcopy(_state)


def reset() -> None:
    global _state
    with _lock:
        _state = _initial()


def audit(actor: str, action: str, detail: dict[str, Any] | None = None) -> None:
    with _lock:
        _state["audit"].insert(0, {"ts": _now(), "actor": actor, "action": action, "detail": detail or {}})
        del _state["audit"][200:]


def add_feed_event(event: dict[str, Any]) -> None:
    with _lock:
        _state["feed"].insert(0, event)
        del _state["feed"][50:]
        _state["kpis"]["transactions_monitored"] += 1


def get_feed_event(tx_id: str) -> dict[str, Any] | None:
    with _lock:
        return next((e for e in _state["feed"] if e["tx_id"] == tx_id), None)


def update_feed_event(tx_id: str, **changes: Any) -> dict[str, Any] | None:
    with _lock:
        for e in _state["feed"]:
            if e["tx_id"] == tx_id:
                e.update(changes)
                return copy.deepcopy(e)
    return None


def open_case(kind: str, customer_id: str, summary: str, ref: str) -> dict[str, Any]:
    with _lock:
        existing = next((c for c in _state["cases"] if c["ref"] == ref), None)
        if existing:
            return copy.deepcopy(existing)
        case = {
            "case_id": f"CASE-{uuid.uuid4().hex[:6].upper()}",
            "kind": kind,
            "customer_id": customer_id,
            "summary": summary,
            "ref": ref,
            "status": "open",
            "opened_at": _now(),
        }
        _state["cases"].insert(0, case)
        _state["kpis"]["open_alerts"] += 1
        return copy.deepcopy(case)


def resolve(rec_id: str | None, savings_usd: float, label: str, kpi_changes: dict[str, float] | None = None,
            exposure: tuple[str, str] | None = None, is_alert: bool = True) -> bool:
    """Apply an intervention once: drop open alerts, add savings, mark the chart, close the exposure."""
    with _lock:
        if rec_id:
            rec = next((r for r in _state["recommendations"] if r["id"] == rec_id), None)
            if rec is None or rec["status"] == "resolved":
                return False
            rec["status"] = "resolved"
        k = _state["kpis"]
        if is_alert:
            k["open_alerts"] = max(0, k["open_alerts"] - 1)
        k["projected_savings_usd"] += savings_usd
        for key, delta in (kpi_changes or {}).items():
            k[key] = max(0, k[key] + delta)
        if savings_usd:
            last = _state["savings_series"][-1]
            last["savings_k"] = round(last["savings_k"] + savings_usd / 1000.0, 1)
            _state["interventions"].append({"index": _state["latest_index"], "label": label, "savings_usd": savings_usd, "ts": _now(), "live": True})
        if exposure:
            update_exposure(exposure[0], status="resolved", progress=100, progress_label=exposure[1])
        return True


def update_exposure(exp_id: str, **changes: Any) -> None:
    with _lock:
        for e in _state["exposures"]:
            if e["id"] == exp_id:
                e.update(changes)
                return


def add_exposure(item: dict[str, Any]) -> None:
    with _lock:
        if not any(e["id"] == item["id"] for e in _state["exposures"]):
            _state["exposures"].insert(0, item)


def recommendation(rec_id: str) -> dict[str, Any] | None:
    with _lock:
        rec = next((r for r in _state["recommendations"] if r["id"] == rec_id), None)
        return copy.deepcopy(rec) if rec else None


def set_value(key: str, value: Any) -> None:
    with _lock:
        _state[key] = value
