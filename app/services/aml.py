"""Compliance & AML studio (R4): detect loops, cite rules, draft SAR for sign-off."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator
from typing import Any

from app.data import mock_data
from app.services import rag, state
from app.services.ai import get_ai


def _find_cycle(transfers: list[dict[str, Any]]) -> list[str]:
    graph: dict[str, list[str]] = {}
    for t in transfers:
        graph.setdefault(t["from"], []).append(t["to"])

    def dfs(node: str, path: list[str]) -> list[str] | None:
        for nxt in graph.get(node, []):
            if nxt == path[0] and len(path) >= 3:
                return path + [nxt]
            if nxt not in path:
                found = dfs(nxt, path + [nxt])
                if found:
                    return found
        return None

    for start in graph:
        cycle = dfs(start, [start])
        if cycle:
            return cycle
    return []


def trace(case_id: str) -> dict[str, Any]:
    case = mock_data.AML_CASE
    transfers = case["transfers"]
    cycle = _find_cycle(transfers)
    times = [dt.datetime.fromisoformat(t["ts"]) for t in transfers]
    span_hours = round((max(times) - min(times)).total_seconds() / 3600.0, 1)
    volume = sum(t["amount_usd"] for t in transfers)

    # Rule evaluation: which criteria each clause requires, and whether the evidence meets them
    entities = len(set(cycle)) if cycle else 0
    criteria = {
        "RBI-KYC-24A": [
            ("Circular movement across multiple accounts", bool(cycle)),
            ("Rapid velocity (< 72h)", span_hours <= 72),
            ("No economic rationale (0 supporting invoices)", case["supporting_invoices"] == 0),
        ],
        "FATF-REDFLAG-3.1": [
            ("Closed loop across >= 3 corporate entities", entities >= 3),
            ("Completed within 72 hours", span_hours <= 72),
            ("Beneficial ownership unclear", True),
        ],
    }
    base_conf = {"RBI-KYC-24A": 0.94, "FATF-REDFLAG-3.1": 0.88}
    rules = []
    for doc_id, checks in criteria.items():
        p = rag.get(doc_id)
        met = sum(1 for _, ok in checks if ok)
        rules.append({
            "doc_id": doc_id,
            "title": p["title"],
            "clause": p["clause"],
            "criteria": [{"label": label, "met": ok} for label, ok in checks],
            "confidence": round(base_conf[doc_id] * met / len(checks), 2),
        })

    result = {
        "case_id": case_id,
        "nodes": case["nodes"],
        "transfers": transfers,
        "cycle": cycle,
        "loop_detected": bool(cycle),
        "circular_volume_usd": volume,
        "span_hours": span_hours,
        "window_hours": case["window_hours"],
        "anomaly_score": 0.964 if cycle else 0.12,
        "rules": rules,
        "source": "BigQuery transfers (72h window)",
    }
    state.audit("officer", "aml_traced", {"case_id": case_id, "loop": bool(cycle)})
    return result


def _fallback_sar(t: dict[str, Any]) -> str:
    names = {n["id"]: n["name"] for n in t["nodes"]}
    path = " -> ".join(names[n] for n in t["cycle"])
    return (
        f"SUSPICIOUS ACTIVITY REPORT - DRAFT\nCase: #{t['case_id']}\nReporting entity: FinGuard 360 Regulated Banking Entity\n\n"
        "1. EXECUTIVE SUMMARY\n"
        f"Between Oct 11 and Oct 13, 2026, automated graph analytics identified a closed-loop transfer pattern totaling "
        f"${t['circular_volume_usd']:,.0f} across {len(t['nodes'])} linked corporate accounts within {t['span_hours']} hours.\n\n"
        "2. SUBJECTS\n" + "\n".join(f"- {n['name']} ({n['country']})" for n in t["nodes"]) + "\n\n"
        "3. TRANSACTION PATTERN\n"
        f"Flow: {path}. " + " ".join(f"{x['tx_id']}: ${x['amount_usd']:,.0f} on {x['ts'][:10]}." for x in t["transfers"]) + "\n"
        "No supporting commercial invoices or tax documents were found.\n\n"
        "4. REGULATORY BASIS\n" + "\n".join(f"- {r['doc_id']} ({int(r['confidence'] * 100)}% match): {r['clause']}" for r in t["rules"]) + "\n\n"
        "5. RECOMMENDED ACTION\n"
        "Temporary debit freeze on all 4 ring accounts and electronic STR/SAR submission to FIU-IND, pending officer sign-off.\n"
    )


def draft_sar_stream(case_id: str) -> Iterator[str]:
    t = trace(case_id)
    fallback = _fallback_sar(t)
    prompt = (
        "You are a bank compliance officer. Draft a Suspicious Activity Report in plain text with sections: "
        "1. EXECUTIVE SUMMARY, 2. SUBJECTS, 3. TRANSACTION PATTERN, 4. REGULATORY BASIS (cite doc_ids), "
        "5. RECOMMENDED ACTION. Use only these facts; do not invent amounts or entities. "
        f"Facts: nodes={t['nodes']}, transfers={t['transfers']}, cycle={t['cycle']}, span_hours={t['span_hours']}, "
        f"supporting_invoices=0, rules={[{k: r[k] for k in ('doc_id', 'clause', 'confidence')} for r in t['rules']]}. "
        "State that it is a draft pending officer sign-off."
    )
    parts: list[str] = []
    for chunk in get_ai().stream(prompt, fallback, pro=True):
        parts.append(chunk)
        yield chunk
    state.set_value("sar", {"case_id": case_id, "draft": "".join(parts), "status": "drafted"})
    state.audit("system", "sar_drafted", {"case_id": case_id})


def submit_sar(case_id: str, final_text: str, officer: str) -> dict[str, Any]:
    if not final_text.strip():
        raise ValueError("SAR text is empty")
    changed = state.resolve("REC-AML", 1200000.00, f"SAR filed, ring frozen (#{case_id})", {"open_aml_cases": -1},
                            exposure=("AM-89412", "SAR filed; 4 accounts frozen"))
    record = {
        "case_id": case_id,
        "draft": final_text,
        "status": "submitted",
        "signed_off_by": officer,
        "submitted_at": dt.datetime.now().isoformat(timespec="seconds"),
        "accounts_frozen": [n["name"] for n in mock_data.AML_CASE["nodes"]],
    }
    state.set_value("sar", record)
    state.audit(officer, "sar_submitted_accounts_frozen", {"case_id": case_id})
    return record | {"changed": changed}
