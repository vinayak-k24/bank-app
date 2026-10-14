"""FraudShield data layer: the teammate's BigQuery pipeline (dataset `fraudshield`).

Pipeline (already on GCP): PaySim -> Pub/Sub "transactions" -> Cloud Run "fraudshield-scorer"
-> BigQuery ML (fraud_classifier + anomaly_kmeans) -> fraudshield.scored_transactions / cases.

Two implementations behind one interface (AGENTS.md rule):
- MockFraudShieldRepo (default, offline): deterministic synthetic data scored with the same formula
  as the Cloud Run scorer, including the C_DEMO_001 demo attack.
- BigQueryFraudShieldRepo (USE_MOCK_BQ=false): reads the real tables/views.

Analyst decisions are append-only (BigQuery cannot reliably UPDATE freshly streamed rows):
the live repo writes fraudshield.case_decisions and reads the latest decision per case.
`label_is_fraud` is ground truth for metrics only and is never returned to analysts.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

from app.config import get_settings

log = logging.getLogger(__name__)

# --- Scoring contract (mirrors Cloud Run fraudshield-scorer; deterministic, never LLM) ---
STEP_UP_THRESHOLD = 0.30
HOLD_THRESHOLD = 0.70
VELOCITY_FLOOR_COUNT = 5
VELOCITY_FLOOR_SCORE = 0.55
FOREIGN_AMOUNT = 50_000
FOREIGN_BOOST = 0.15
HOME_COUNTRY = "IN"
ANOMALY_SCALE = 6.0

DECISIONS = ("APPROVED", "REJECTED", "ESCALATED")
FINAL_STATUSES = ("APPROVED", "REJECTED")

DEMO_CUSTOMER = "C_DEMO_001"
DEMO_CASE_ID = "CASE-1A2B3C4D"
DEMO_TXN_ID = "T9bc0e41a22"
DEMO_DEVICE = "dev-ATTACK-77"
DEMO_MULE = "C_MULE_9"


class CaseNotFound(Exception):
    pass


class CaseAlreadyDecided(Exception):
    pass


class DataSourceError(Exception):
    """Live data source failed (BigQuery unreachable, permissions, missing table)."""


def risk_score(fraud_prob: float, anomaly_distance: float, velocity_1h: int, country: str, amount: float) -> float:
    score = 0.8 * fraud_prob + 0.2 * min(anomaly_distance / ANOMALY_SCALE, 1.0)
    if velocity_1h >= VELOCITY_FLOOR_COUNT:
        score = max(score, VELOCITY_FLOOR_SCORE)
    if country != HOME_COUNTRY and amount > FOREIGN_AMOUNT:
        score += FOREIGN_BOOST
    return round(min(max(score, 0.0), 1.0), 4)


def route(score: float) -> str:
    if score >= HOLD_THRESHOLD:
        return "HOLD"
    if score >= STEP_UP_THRESHOLD:
        return "STEP_UP"
    return "APPROVE"


def case_id_for(txn_id: str) -> str:
    if txn_id == DEMO_TXN_ID:
        return DEMO_CASE_ID
    return "CASE-" + hashlib.sha1(txn_id.encode()).hexdigest()[:8].upper()


def iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return str(value)


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _parse_summary(value: Any) -> dict[str, Any] | None:
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(value)
        if isinstance(parsed, str):  # STRING column wrapped by TO_JSON_STRING
            parsed = json.loads(parsed)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


def build_rings(links: list[dict[str, Any]], held_customers: set[str]) -> dict[str, Any]:
    """Graph of customers, devices and receiving accounts linked to held activity."""
    nodes: dict[str, str] = {}
    edges: set[tuple[str, str]] = set()
    for link in links:
        cust, dev, dest = link.get("customer_id"), link.get("device_id"), link.get("dest_id")
        if not cust:
            continue
        nodes.setdefault(cust, "customer")
        if dev:
            nodes.setdefault(dev, "device")
            edges.add((cust, dev))
        if dest:
            nodes.setdefault(dest, "customer" if dest in held_customers else "account")
            edges.add((cust, dest))
    return {
        "nodes": [{"id": k, "kind": v} for k, v in nodes.items()],
        "edges": [{"source": s, "target": t} for s, t in sorted(edges)],
    }


class FraudShieldRepo(Protocol):
    mode: str

    def metrics(self) -> dict[str, Any]: ...
    def transactions(self, limit: int) -> list[dict[str, Any]]: ...
    def cases(self, status: str | None, limit: int) -> list[dict[str, Any]]: ...
    def case(self, case_id: str) -> dict[str, Any]: ...
    def decide(self, case_id: str, decision: str, note: str) -> dict[str, Any]: ...
    def rings(self) -> dict[str, Any]: ...


def _public_txn(t: dict[str, Any]) -> dict[str, Any]:
    out = {
        "txn_id": t["txn_id"], "customer_id": t["customer_id"], "dest_id": t.get("dest_id"),
        "type": t["type"], "amount": float(t["amount"]), "country": t["country"],
        "device_id": t.get("device_id"), "velocity_1h": t.get("velocity_1h"),
        "fraud_prob": t.get("fraud_prob"), "anomaly_distance": t.get("anomaly_distance"),
        "risk_score": float(t["risk_score"]), "decision": t["decision"], "ts": iso(t["ts"]),
    }
    if t.get("case_id"):
        out["case_id"] = t["case_id"]
    return out


class MockFraudShieldRepo:
    mode = "mock"
    BASE_TS = datetime(2026, 10, 14, 10, 35, 2, tzinfo=timezone.utc)

    def __init__(self, n_background: int = 240, seed: int = 42) -> None:
        self._lock = threading.RLock()
        self._decisions: dict[str, dict[str, Any]] = {}
        self._txns = self._generate(n_background, seed)
        self._cases = {
            t["case_id"]: {
                "case_id": t["case_id"], "txn_id": t["txn_id"], "customer_id": t["customer_id"],
                "opened_at": t["ts"] + timedelta(seconds=1), "risk_score": t["risk_score"],
                "status": "OPEN", "ai_summary": None,
            }
            for t in self._txns if t["decision"] == "HOLD"
        }

    def _generate(self, n: int, seed: int) -> list[dict[str, Any]]:
        rng = random.Random(seed)
        types = ["PAYMENT", "PAYMENT", "PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN"]
        txns: list[dict[str, Any]] = []

        def add(ts, cust, dest, typ, amount, country, device, vel, p, dist, label):
            score = risk_score(p, dist, vel, country, amount)
            decision = route(score)
            txn_id = "T" + hashlib.sha1(f"{seed}-{len(txns)}-{cust}".encode()).hexdigest()[:10]
            txns.append({
                "txn_id": txn_id, "customer_id": cust, "dest_id": dest, "ts": ts, "type": typ,
                "amount": round(amount, 2), "country": country, "device_id": device, "velocity_1h": vel,
                "fraud_prob": round(p, 4), "anomaly_distance": round(dist, 3), "risk_score": score,
                "decision": decision, "case_id": None, "label_is_fraud": label,
            })
            return txns[-1]

        start = self.BASE_TS - timedelta(hours=2)
        for i in range(n):
            ts = start + timedelta(seconds=int(i * 7200 / n))
            cust = f"C{rng.randint(1_000_000_000, 1_999_999_999)}"
            dest = f"{'M' if rng.random() < 0.4 else 'C'}{rng.randint(1_000_000_000, 1_999_999_999)}"
            roll = rng.random()
            if roll < 0.04:  # fraud-like: big cash-out, high classifier score
                add(ts, cust, dest, rng.choice(["TRANSFER", "CASH_OUT"]), rng.uniform(80_000, 600_000),
                    rng.choice(["IN", "IN", "AE", "SG"]), f"dev-{rng.randint(100, 999)}",
                    rng.randint(1, 6), rng.uniform(0.75, 0.97), rng.uniform(3, 9), 1)
            elif roll < 0.12:  # unusual but mostly legitimate -> step-up band
                add(ts, cust, dest, rng.choice(types), rng.uniform(20_000, 200_000),
                    rng.choice(["IN", "IN", "IN", "GB"]), f"dev-{rng.randint(100, 999)}",
                    rng.randint(1, 4), rng.uniform(0.3, 0.6), rng.uniform(2, 6), 0)
            else:
                add(ts, cust, dest, rng.choice(types), rng.uniform(50, 60_000), "IN",
                    f"dev-{rng.randint(100, 999)}", rng.randint(0, 3), rng.uniform(0.0, 0.2),
                    rng.uniform(0.2, 2.5), 0)

        # Mule ring sharing the attack device and beneficiary (for the ring view).
        add(self.BASE_TS - timedelta(minutes=12), "C_RING_2", DEMO_MULE, "TRANSFER", 95_000.0, "AE",
            DEMO_DEVICE, 2, 0.70, 4.0, 1)
        # Demo attack: 99 test charge, then 248,000 drain to a new AE account 3 s later, same device.
        add(self.BASE_TS - timedelta(seconds=3), DEMO_CUSTOMER, "M_TEST_MERCHANT", "PAYMENT", 99.0, "IN",
            DEMO_DEVICE, 1, 0.05, 1.2, 1)
        attack = add(self.BASE_TS, DEMO_CUSTOMER, DEMO_MULE, "TRANSFER", 248_000.0, "AE",
                     DEMO_DEVICE, 2, 0.80, 4.5, 1)
        attack["txn_id"] = DEMO_TXN_ID

        for t in txns:
            if t["decision"] == "HOLD":
                t["case_id"] = case_id_for(t["txn_id"])
        return txns

    def _case_view(self, c: dict[str, Any]) -> dict[str, Any]:
        t = next(x for x in self._txns if x["txn_id"] == c["txn_id"])
        d = self._decisions.get(c["case_id"])
        return {
            "case_id": c["case_id"], "txn_id": c["txn_id"], "customer_id": c["customer_id"],
            "amount": t["amount"], "type": t["type"], "country": t["country"], "device_id": t["device_id"],
            "dest_id": t["dest_id"], "risk_score": c["risk_score"],
            "status": d["decision"] if d else c["status"], "opened_at": iso(c["opened_at"]),
            "ai_summary": c["ai_summary"],
            "analyst_decision": d["decision"] if d else None,
            "analyst_note": d["note"] if d else None,
            "decided_at": iso(d["decided_at"]) if d else None,
        }

    def metrics(self) -> dict[str, Any]:
        with self._lock:
            counts = {"APPROVE": 0, "STEP_UP": 0, "HOLD": 0}
            for t in self._txns:
                counts[t["decision"]] += 1
            open_cases = sum(1 for c in self._cases.values() if self._case_view(c)["status"] == "OPEN")
            return {
                "transactions_scored": len(self._txns),
                "held_count": counts["HOLD"],
                "amount_held": round(sum(t["amount"] for t in self._txns if t["decision"] == "HOLD"), 2),
                "open_cases": open_cases,
                "step_up_count": counts["STEP_UP"],
                "decision_breakdown": counts,
                "as_of": iso(max(t["ts"] for t in self._txns)),
            }

    def transactions(self, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            ordered = sorted(self._txns, key=lambda t: t["ts"], reverse=True)[:limit]
            return [_public_txn(t) for t in ordered]

    def cases(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        with self._lock:
            rows = [self._case_view(c) for c in self._cases.values()]
        if status:
            rows = [r for r in rows if r["status"] == status]
        rows.sort(key=lambda r: r["risk_score"], reverse=True)
        return rows[:limit]

    def case(self, case_id: str) -> dict[str, Any]:
        with self._lock:
            if case_id not in self._cases:
                raise CaseNotFound(case_id)
            return self._case_view(self._cases[case_id])

    def decide(self, case_id: str, decision: str, note: str) -> dict[str, Any]:
        with self._lock:
            current = self.case(case_id)
            if current["status"] in FINAL_STATUSES:
                raise CaseAlreadyDecided(current["status"])
            decided_at = _now()
            self._decisions[case_id] = {"decision": decision, "note": note, "decided_at": decided_at}
            return {"case_id": case_id, "status": decision, "decided_at": iso(decided_at)}

    def rings(self) -> dict[str, Any]:
        with self._lock:
            held = [t for t in self._txns if t["decision"] == "HOLD"]
            devices = {t["device_id"] for t in held}
            dests = {t["dest_id"] for t in held}
            links = [t for t in self._txns
                     if t["decision"] == "HOLD" or t["device_id"] in devices or t["dest_id"] in dests]
            return build_rings(links, {t["customer_id"] for t in held})


class BigQueryFraudShieldRepo:
    mode = "bigquery"

    def __init__(self) -> None:
        from google.cloud import bigquery  # imported lazily so mock mode needs no GCP libs

        s = get_settings()
        self._bq = bigquery
        self._project = s.bq_project_id or s.gcp_project_id
        self._prefix = f"{self._project}.{s.bq_dataset}"
        self._decisions_table = f"{self._prefix}.case_decisions"
        self._client = bigquery.Client(project=self._project, location=s.bq_location)
        self._lock = threading.Lock()
        self._decisions_ready = False

    def _t(self, name: str) -> str:
        return f"`{self._prefix}.{name}`"

    def _query(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        try:
            job = self._client.query(sql, job_config=self._bq.QueryJobConfig(query_parameters=params or []))
            return [dict(row.items()) for row in job.result()]
        except Exception as exc:  # surfaced as 503 by the router
            log.exception("BigQuery query failed")
            raise DataSourceError(str(exc)) from exc

    def _ensure_decisions_table(self) -> None:
        with self._lock:
            if self._decisions_ready:
                return
            self._query(
                f"CREATE TABLE IF NOT EXISTS `{self._decisions_table}` ("
                "case_id STRING NOT NULL, decision STRING NOT NULL, note STRING, "
                "analyst STRING, decided_at TIMESTAMP NOT NULL)"
            )
            self._decisions_ready = True

    def _cases_sql(self, where: str) -> str:
        return f"""
        WITH latest AS (
          SELECT case_id, ARRAY_AGG(STRUCT(decision, note, decided_at) ORDER BY decided_at DESC LIMIT 1)[OFFSET(0)] AS d
          FROM `{self._decisions_table}` GROUP BY case_id
        ), c AS (
          SELECT c.case_id, c.txn_id, c.customer_id, c.opened_at, c.risk_score,
                 COALESCE(l.d.decision, c.status) AS status,
                 TO_JSON_STRING(c.ai_summary) AS ai_summary,
                 COALESCE(l.d.decision, c.analyst_decision) AS analyst_decision,
                 l.d.note AS analyst_note,
                 COALESCE(l.d.decided_at, c.decided_at) AS decided_at,
                 t.amount, t.type, t.country, t.device_id, t.dest_id
          FROM {self._t('cases')} c
          LEFT JOIN {self._t('scored_transactions')} t USING (txn_id)
          LEFT JOIN latest l USING (case_id)
        )
        SELECT * FROM c {where}
        """

    def _case_row(self, r: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_id": r["case_id"], "txn_id": r["txn_id"], "customer_id": r["customer_id"],
            "amount": float(r["amount"]) if r.get("amount") is not None else None,
            "type": r.get("type"), "country": r.get("country"), "device_id": r.get("device_id"),
            "dest_id": r.get("dest_id"), "risk_score": float(r["risk_score"]), "status": r["status"],
            "opened_at": iso(r["opened_at"]), "ai_summary": _parse_summary(r.get("ai_summary")),
            "analyst_decision": r.get("analyst_decision"), "analyst_note": r.get("analyst_note"),
            "decided_at": iso(r.get("decided_at")),
        }

    def metrics(self) -> dict[str, Any]:
        self._ensure_decisions_table()
        txn = self._query(f"""
            SELECT COUNT(*) AS n, COUNTIF(decision='HOLD') AS hold, COUNTIF(decision='STEP_UP') AS step_up,
                   COUNTIF(decision='APPROVE') AS approve, IFNULL(SUM(IF(decision='HOLD', amount, 0)), 0) AS held_amt,
                   MAX(ts) AS as_of
            FROM {self._t('scored_transactions')}""")[0]
        open_sql = self._cases_sql("WHERE status = 'OPEN'")
        open_cases = self._query(f"SELECT COUNT(*) AS n FROM ({open_sql})")[0]["n"]
        return {
            "transactions_scored": int(txn["n"]), "held_count": int(txn["hold"]),
            "amount_held": float(txn["held_amt"]), "open_cases": int(open_cases),
            "step_up_count": int(txn["step_up"]),
            "decision_breakdown": {"APPROVE": int(txn["approve"]), "STEP_UP": int(txn["step_up"]),
                                   "HOLD": int(txn["hold"])},
            "as_of": iso(txn["as_of"]) or iso(_now()),
        }

    def transactions(self, limit: int) -> list[dict[str, Any]]:
        rows = self._query(
            f"""SELECT txn_id, customer_id, dest_id, ts, type, amount, country, device_id, velocity_1h,
                       fraud_prob, anomaly_distance, risk_score, decision, case_id
                FROM {self._t('scored_transactions')} ORDER BY ts DESC LIMIT @limit""",
            [self._bq.ScalarQueryParameter("limit", "INT64", limit)],
        )
        return [_public_txn(r) for r in rows]

    def cases(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        self._ensure_decisions_table()
        params = [self._bq.ScalarQueryParameter("limit", "INT64", limit)]
        where = ""
        if status:
            where = "WHERE status = @status"
            params.append(self._bq.ScalarQueryParameter("status", "STRING", status))
        rows = self._query(self._cases_sql(where) + " ORDER BY risk_score DESC LIMIT @limit", params)
        return [self._case_row(r) for r in rows]

    def case(self, case_id: str) -> dict[str, Any]:
        self._ensure_decisions_table()
        rows = self._query(self._cases_sql("WHERE case_id = @case_id"),
                           [self._bq.ScalarQueryParameter("case_id", "STRING", case_id)])
        if not rows:
            raise CaseNotFound(case_id)
        return self._case_row(rows[0])

    def decide(self, case_id: str, decision: str, note: str) -> dict[str, Any]:
        current = self.case(case_id)
        if current["status"] in FINAL_STATUSES:
            raise CaseAlreadyDecided(current["status"])
        decided_at = _now()
        P = self._bq.ScalarQueryParameter
        # DML insert (not streaming) so the decision is readable immediately.
        self._query(
            f"INSERT INTO `{self._decisions_table}` (case_id, decision, note, analyst, decided_at) "
            "VALUES (@case_id, @decision, @note, @analyst, @decided_at)",
            [P("case_id", "STRING", case_id), P("decision", "STRING", decision), P("note", "STRING", note),
             P("analyst", "STRING", "analyst"), P("decided_at", "TIMESTAMP", decided_at)],
        )
        return {"case_id": case_id, "status": decision, "decided_at": iso(decided_at)}

    def rings(self) -> dict[str, Any]:
        st = self._t("scored_transactions")
        links = self._query(f"""
            WITH held AS (SELECT customer_id, device_id, dest_id FROM {st}
                          WHERE decision = 'HOLD' ORDER BY ts DESC LIMIT 200)
            SELECT DISTINCT customer_id, device_id, dest_id FROM {st}
            WHERE device_id IN (SELECT device_id FROM held) OR dest_id IN (SELECT dest_id FROM held)
            LIMIT 1000""")
        held = self._query(f"SELECT DISTINCT customer_id FROM {st} WHERE decision = 'HOLD' LIMIT 1000")
        return build_rings(links, {r["customer_id"] for r in held})


_repo: FraudShieldRepo | None = None
_repo_lock = threading.Lock()


def get_repo() -> FraudShieldRepo:
    global _repo
    with _repo_lock:
        if _repo is None:
            if get_settings().live_bq:
                try:
                    _repo = BigQueryFraudShieldRepo()
                except Exception:
                    log.exception("BigQuery client init failed; using mock FraudShield data")
                    _repo = MockFraudShieldRepo()
            else:
                _repo = MockFraudShieldRepo()
        return _repo


def reset_repo() -> None:
    global _repo
    with _repo_lock:
        _repo = None
