import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import state


@pytest.fixture(autouse=True)
def fresh_state():
    state.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def test_health_and_index(client):
    assert client.get("/api/health").json()["ai_mode"] == "mock"
    assert "FinGuard 360" in client.get("/").text


def test_new_device_payment_held_at_95(client):
    e = client.post("/api/payments", json={"customer_id": "CUST-101", "recipient": "Offshore Transit Ltd", "amount_usd": 48500, "new_device": True}).json()
    assert e["risk_pct"] == 95
    assert e["status"] == "on_hold"
    assert "not frozen" in e["explanation"]


def test_normal_payment_approved(client):
    e = client.post("/api/payments", json={"customer_id": "CUST-101", "recipient": "Metro Utilities", "amount_usd": 120, "new_device": False}).json()
    assert e["decision"] == "APPROVED" and e["risk_pct"] == 10


def test_block_hold_updates_kpis(client):
    before = client.get("/api/state").json()["kpis"]
    e = client.post("/api/payments", json={"customer_id": "CUST-101", "recipient": "Offshore Transit Ltd", "amount_usd": 48500, "new_device": True}).json()
    r = client.post(f"/api/payments/{e['tx_id']}/resolve", json={"action": "block"}).json()
    assert r["status"] == "blocked"
    after = client.get("/api/state").json()["kpis"]
    assert after["fraud_blocked_count"] == before["fraud_blocked_count"] + 1
    assert after["projected_savings_usd"] == before["projected_savings_usd"] + 48500


def test_invalid_hold_action_rejected(client):
    assert client.post("/api/payments/TX-NOPE/resolve", json={"action": "delete"}).status_code == 422


def test_scam_scan_flags_account_and_domain(client):
    r = client.post("/api/scam/scan").json()
    fields = {f["field"]: f for f in r["findings"]}
    assert r["verdict"] == "SCAM_LIKELY"
    assert fields["Bank account"]["found"].endswith("8841")
    assert fields["Sender domain"]["found"] == "netcorp-pay.co"


def test_upload_type_rejected(client):
    r = client.post("/api/scam/scan", files={"file": ("x.exe", b"MZ", "application/octet-stream")})
    assert r.status_code == 415


def test_clean_statement_preapproved(client):
    r = client.post("/api/documents/analyze", data={"kind": "clean"}).json()
    assert r["verdict"] == "INSTANT_PRE_APPROVED"
    assert r["ledger_check"]["declared_monthly_deposits_usd"] == r["ledger_check"]["ledger_monthly_deposits_usd"] == 14250
    assert r["offer"]["limit_usd"] == 45000


def test_tampered_statement_flagged(client):
    r = client.post("/api/documents/analyze", data={"kind": "tampered"}).json()
    assert r["verdict"] == "MANUAL_STEP_UP_REQUIRED"
    assert r["ledger_check"]["declared_monthly_deposits_usd"] == 18500
    assert r["ledger_check"]["ledger_monthly_deposits_usd"] == 12400
    assert r["policy_citation"]["doc_id"] == "UW-POLICY-104"
    assert r["next_action"] == "Request Tax/GST Proof"


def test_loan_quote(client):
    q = client.post("/api/loans/quote", json={"amount_usd": 45000, "apr_pct": 6.45, "term_months": 24}).json()
    assert 1990 < q["monthly_payment_usd"] < 2010
    assert client.post("/api/loans/quote", json={"amount_usd": 45000, "apr_pct": 6.45, "term_months": 48}).status_code == 422


def test_aml_trace_detects_loop(client):
    t = client.get("/api/aml/cases/AM-89412/trace").json()
    assert t["loop_detected"] and t["cycle"][0] == t["cycle"][-1]
    assert t["circular_volume_usd"] == 1200000
    assert {r["doc_id"]: r["confidence"] for r in t["rules"]} == {"RBI-KYC-24A": 0.94, "FATF-REDFLAG-3.1": 0.88}


def test_sar_stream_and_submit(client):
    text = client.get("/api/aml/cases/AM-89412/sar/stream").text
    assert "RBI-KYC-24A" in text and "EXECUTIVE SUMMARY" in text
    before = client.get("/api/state").json()["kpis"]
    r = client.post("/api/aml/cases/AM-89412/sar/submit", json={"text": text, "officer": "Alex"}).json()
    assert r["status"] == "submitted" and len(r["accounts_frozen"]) == 4
    after = r["state"]["kpis"]
    assert after["open_aml_cases"] == before["open_aml_cases"] - 1
    assert after["open_alerts"] == before["open_alerts"] - 1


def test_coach_forecast_12_day_gap(client):
    fc = client.get("/api/coach/CUST-101/forecast").json()
    assert fc["dip"]["detected"] and fc["dip"]["gap_days"] == 12
    later = client.get("/api/coach/CUST-101/forecast?delay_days=5").json()
    assert later["dip"]["gap_days"] > 12


def test_coach_disabled_for_aml_persona(client):
    assert client.get("/api/coach/AML-303/forecast").json()["available"] is False


def test_eligibility_credit_line(client):
    r = client.post("/api/coach/eligibility", json={"customer_id": "CUST-101", "product_id": "PROD-INV-FIN-01"}).json()
    assert r["eligible"] and "6.45" in r["explanation"] and "12-day" in r["explanation"]


def test_recommendations_resolve_once(client):
    r1 = client.post("/api/command/actions/REC-SCAM/execute").json()
    r2 = client.post("/api/command/actions/REC-SCAM/execute").json()
    assert r1["changed"] is True and r2["changed"] is False
    assert len([i for i in r2["state"]["interventions"] if i["live"]]) == 1
    assert client.post("/api/command/actions/NOPE/execute").status_code == 404


def test_copilot_context_answers(client):
    r = client.post("/api/copilot/chat", json={"message": "Why was Apex Mfg's bank statement flagged?", "page": "documents"}).json()
    assert "18,500" in r["reply"] and "UW-104" in r["reply"]
    assert "Summarize RBI KYC Sec 24(a)" in client.get("/api/copilot/suggestions?page=compliance").json()


@pytest.mark.parametrize("pid,expected_pct", [("CUST-101", 95), ("SME-202", 78), ("AML-303", 80)])
def test_each_persona_scenario_payment_is_held(client, pid, expected_pct):
    sc = next(p for p in client.get("/api/personas").json() if p["customer_id"] == pid)["scenario"]["payment"]
    e = client.post("/api/payments", json={"customer_id": pid, **sc}).json()
    assert e["status"] == "on_hold" and e["risk_pct"] == expected_pct


def test_feed_filtered_by_persona(client):
    client.post("/api/payments/tick?customer_id=CUST-101")
    client.post("/api/payments/tick?customer_id=SME-202")
    feed = client.get("/api/payments/feed?customer_id=SME-202").json()
    assert feed and all(e["customer_id"] == "SME-202" for e in feed)


def test_persona_aware_briefing_and_suggestions(client):
    assert "Apex" in client.get("/api/command/briefing?persona_id=SME-202").json()["briefing"]
    assert client.get("/api/copilot/suggestions?page=documents&persona_id=CUST-101").json()[0] == "Is Aarav's statement genuine?"
    r = client.post("/api/copilot/chat", json={"message": "Is Aarav's statement genuine?", "page": "documents", "persona_id": "CUST-101"}).json()
    assert "14,250" in r["reply"]


def test_global_view_persona_listed_first(client):
    ps = client.get("/api/personas").json()
    assert ps[0]["customer_id"] == "ALL" and len(ps) == 4


def test_dashboard_ranked_alerts_and_divisions(client):
    d = client.get("/api/dashboard").json()
    ranked = d["ranked_alerts"]
    assert ranked[0]["id"] == "AM-89412"
    assert [a["exposure_usd"] for a in ranked] == sorted([a["exposure_usd"] for a in ranked], reverse=True)
    assert {x["id"] for x in d["divisions"]} == {"retail", "sme", "insurance", "treasury"}
    assert any(s["name"].startswith("Gemini") and s["mode"] == "mock" for s in d["services"])
    assert len(d["analytics"]["threats"]) == 4


def test_dashboard_persona_filter(client):
    d = client.get("/api/dashboard?persona_id=SME-202").json()
    assert d["ranked_alerts"] and all(a["customer_id"] == "SME-202" for a in d["ranked_alerts"])


def test_sar_submission_clears_alert_and_raises_treasury_health(client):
    before = {x["id"]: x["health"] for x in client.get("/api/dashboard").json()["divisions"]}
    client.post("/api/command/actions/REC-AML/execute")
    d = client.get("/api/dashboard").json()
    assert all(a["id"] != "AM-89412" for a in d["ranked_alerts"])
    assert {x["id"]: x["health"] for x in d["divisions"]}["treasury"] > before["treasury"]
    assert any(i["live"] and "SAR" in i["label"] for i in d["interventions"])


def test_growth_action_adds_revenue_not_savings(client):
    before = client.get("/api/state").json()["kpis"]
    r = client.post("/api/command/actions/REC-GROWTH/execute").json()
    k = r["state"]["kpis"]
    assert r["changed"] and k["growth_offers_sent"] == 340 and k["growth_nii_usd"] == 410000
    assert k["projected_savings_usd"] == before["projected_savings_usd"] and k["open_alerts"] == before["open_alerts"]


def test_inflated_claim_routed_to_adjuster(client):
    r = client.post("/api/documents/analyze", data={"kind": "claim_inflated"}).json()
    assert r["doc_type"] == "claim" and r["verdict"] == "ROUTE_TO_ADJUSTER"
    assert r["ledger_check"]["declared_usd"] == 175000 and r["ledger_check"]["ledger_usd"] == 112500
    assert r["payout_usd"] == 107500 and r["policy_citation"]["doc_id"] == "CLM-POL-12"
    route = client.post("/api/claims/claim_inflated/route").json()
    assert route["changed"] and route["avoided_usd"] == 67500
    assert client.post("/api/claims/claim_inflated/route").json()["changed"] is False


def test_clean_claim_auto_approved(client):
    r = client.post("/api/documents/analyze", data={"kind": "claim_clean"}).json()
    assert r["verdict"] == "AUTO_APPROVED" and r["payout_usd"] == 1750
    assert client.post("/api/claims/claim_clean/payout").json()["payout_usd"] == 1750
    assert client.post("/api/claims/claim_inflated/payout").status_code == 409


def test_search_finds_cases_and_policies(client):
    types = {h["type"] for h in client.get("/api/search?q=apex").json()}
    assert {"Customer", "Case"} <= types
    assert client.get("/api/search?q=UW-104").json()[0]["type"] == "Policy"
    assert client.get("/api/search?q=a").json() == []
