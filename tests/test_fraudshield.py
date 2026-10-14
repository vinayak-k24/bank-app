import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import fraudshield as fs
from app.services import state


@pytest.fixture(autouse=True)
def fresh_state():
    state.reset()
    fs.reset_repo()
    yield


@pytest.fixture
def client():
    return TestClient(app)


# --- Scoring contract (mirrors Cloud Run fraudshield-scorer) ---

def test_blend_formula_and_routing_bands():
    assert fs.risk_score(0.1, 1.5, 0, "IN", 100) == pytest.approx(0.13)
    assert fs.route(0.2999) == "APPROVE"
    assert fs.route(0.30) == "STEP_UP"
    assert fs.route(0.6999) == "STEP_UP"
    assert fs.route(0.70) == "HOLD"


def test_rule_boosts():
    assert fs.risk_score(0.0, 0.0, 5, "IN", 100) == 0.55          # velocity floor
    assert fs.risk_score(0.0, 0.0, 4, "IN", 100) == 0.0
    assert fs.risk_score(0.0, 0.0, 0, "AE", 50_001) == 0.15       # foreign > 50,000
    assert fs.risk_score(0.0, 0.0, 0, "AE", 50_000) == 0.0
    assert fs.risk_score(1.0, 99, 9, "AE", 1e6) == 1.0            # capped


def test_demo_attack_is_held_with_case(client):
    feed = client.get("/transactions?limit=2").json()
    attack, test_charge = feed[0], feed[1]
    assert attack["txn_id"] == fs.DEMO_TXN_ID
    assert attack["customer_id"] == "C_DEMO_001"
    assert attack["amount"] == 248000.0 and attack["country"] == "AE"
    assert attack["risk_score"] == 0.94 and attack["decision"] == "HOLD"
    assert attack["case_id"] == "CASE-1A2B3C4D"
    assert test_charge["amount"] == 99.0 and test_charge["decision"] == "APPROVE"
    assert test_charge["device_id"] == attack["device_id"] == "dev-ATTACK-77"
    assert "case_id" not in test_charge
    assert all("label_is_fraud" not in t for t in client.get("/transactions?limit=500").json())


def test_metrics_are_consistent(client):
    m = client.get("/metrics").json()
    b = m["decision_breakdown"]
    assert set(m) == {"transactions_scored", "held_count", "amount_held", "open_cases",
                      "step_up_count", "decision_breakdown", "as_of"}
    assert sum(b.values()) == m["transactions_scored"]
    assert b["HOLD"] == m["held_count"] == m["open_cases"] >= 1
    assert b["STEP_UP"] == m["step_up_count"]
    assert m["amount_held"] >= 248000.0
    assert m["as_of"] == "2026-10-14T10:35:02Z"


def test_case_queue_sorted_and_detail(client):
    queue = client.get("/cases?status=OPEN").json()
    assert queue and all(c["status"] == "OPEN" for c in queue)
    assert [c["risk_score"] for c in queue] == sorted((c["risk_score"] for c in queue), reverse=True)
    demo = client.get("/cases/CASE-1A2B3C4D").json()
    assert demo["txn_id"] == fs.DEMO_TXN_ID and demo["device_id"] == "dev-ATTACK-77"
    assert demo["type"] == "TRANSFER" and demo["amount"] == 248000.0
    assert demo["ai_summary"] is None
    assert client.get("/cases/CASE-NOPE").status_code == 404
    assert client.get("/cases?status=BOGUS").status_code == 422


def test_decision_flow(client):
    open_before = client.get("/metrics").json()["open_cases"]
    r = client.post("/cases/CASE-1A2B3C4D/decision",
                    json={"decision": "REJECTED", "note": "Customer confirmed not authorised"})
    assert r.status_code == 200
    body = r.json()
    assert body["case_id"] == "CASE-1A2B3C4D" and body["status"] == "REJECTED"
    assert body["decided_at"].endswith("Z")
    detail = client.get("/cases/CASE-1A2B3C4D").json()
    assert detail["status"] == "REJECTED" and detail["analyst_note"] == "Customer confirmed not authorised"
    assert client.get("/metrics").json()["open_cases"] == open_before - 1
    assert all(c["case_id"] != "CASE-1A2B3C4D" for c in client.get("/cases?status=OPEN").json())
    assert client.post("/cases/CASE-1A2B3C4D/decision", json={"decision": "APPROVED"}).status_code == 409
    assert client.post("/cases/CASE-NOPE/decision", json={"decision": "APPROVED"}).status_code == 404
    assert any("FraudShield" in a["action"] for a in state.snapshot()["audit"])


def test_escalated_case_can_still_be_decided(client):
    assert client.post("/cases/CASE-1A2B3C4D/decision", json={"decision": "ESCALATED"}).json()["status"] == "ESCALATED"
    assert client.post("/cases/CASE-1A2B3C4D/decision", json={"decision": "APPROVED"}).status_code == 200


@pytest.mark.parametrize("bad", ["APPROVE", "OPEN", "rejected", ""])
def test_decision_values_validated(client, bad):
    assert client.post("/cases/CASE-1A2B3C4D/decision", json={"decision": bad}).status_code == 422


def test_rings_link_attack_device_and_mule(client):
    g = client.get("/rings").json()
    kinds = {n["id"]: n["kind"] for n in g["nodes"]}
    edges = {(e["source"], e["target"]) for e in g["edges"]}
    assert kinds["C_DEMO_001"] == "customer" and kinds["dev-ATTACK-77"] == "device"
    assert kinds["C_MULE_9"] == "account"
    assert ("C_DEMO_001", "dev-ATTACK-77") in edges and ("C_DEMO_001", "C_MULE_9") in edges
    assert ("C_RING_2", "dev-ATTACK-77") in edges  # second customer on the same device


def test_api_fs_mirror_and_chat_stub(client):
    assert client.get("/api/fs/metrics").json() == client.get("/metrics").json()
    assert client.post("/cases/CASE-1A2B3C4D/chat", json={"message": "other txns on this device?"}).status_code == 501
    assert client.post("/cases/CASE-NOPE/chat", json={"message": "hi"}).status_code == 404


def test_cors_allows_frontend_origin(client):
    r = client.get("/metrics", headers={"Origin": "http://localhost:3000"})
    assert r.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_optional_api_key(client, monkeypatch):
    monkeypatch.setattr(fs.get_settings(), "api_key", "demo-key")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "demo-key"}).status_code == 200


def test_health_reports_data_mode(client):
    assert client.get("/api/health").json()["data_mode"] == "mock"
