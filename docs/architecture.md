# Architecture

## Built layout (2026-10-14)
```
app/
  main.py                 # FastAPI routes + serves static/
  config.py               # env settings (USE_MOCK_AI, GEMINI_API_KEY, USE_VERTEX, GCP_*)
  data/mock_data.py       # personas, documents, scam invoice, policies, products, AML case, KPIs
  services/
    ai.py                 # AIProvider: mock | Gemini API | Vertex (google-genai); always has fallback
    state.py              # shared in-memory state: KPIs, recommendations, feed, cases, audit, SAR
    fraud.py              # R1 scoring, hold/confirm/block, multimodal invoice scan
    underwriting.py       # R3 extract -> ledger check -> verdict, loan quote
    aml.py                # R4 loop detection, rule matching, SAR stream/submit
    coach.py              # R2 30-day forecast, what-if, product eligibility
    rag.py                # policy retrieval (Vertex AI Search stand-in)
    command.py            # briefing, recommended actions, copilot
static/  index.html, styles.css, charts.js, app.js
tests/test_api.py         # 17 tests pinning demo numbers and cross-page state
```

## API
| Method | Path | Page |
|---|---|---|
| GET | /api/health, /api/personas, /api/state · POST /api/state/reset | shell |
| GET | /api/command/briefing · POST /api/command/actions/{rec_id}/execute | 1 |
| POST | /api/payments · /api/payments/tick · /api/payments/{tx}/resolve · /api/scam/scan · /api/scam/block · GET /api/payments/feed | 2 |
| POST | /api/documents/analyze (multipart) · /api/loans/quote · /api/loans/request-proof | 3 |
| GET | /api/aml/cases/{id}/trace · /api/aml/cases/{id}/sar/stream · POST .../sar/submit | 4 |
| GET | /api/coach/{cid}/forecast · /api/coach/{cid}/products · POST /api/coach/eligibility | 5 |
| GET | /api/copilot/suggestions · POST /api/copilot/chat | Copilot |

## FraudShield pipeline (teammate, live on GCP since 2026-10-14)
```
PaySim -> Pub/Sub "transactions" -> Cloud Run "fraudshield-scorer"
          -> BigQuery ML fraud_classifier (boosted tree) + anomaly_kmeans
          -> BigQuery dataset fraudshield: scored_transactions, cases, v_decision_summary, v_open_cases
```
- Score: `0.8*fraud_prob + 0.2*min(anomaly_distance/6, 1)`; velocity_1h >= 5 floors at 0.55; non-IN and amount > 50,000 adds 0.15. APPROVE < 0.30 <= STEP_UP < 0.70 <= HOLD (opens a case).
- `app/services/fraudshield.py`: `MockFraudShieldRepo` (default, same formula, C_DEMO_001 attack -> CASE-1A2B3C4D at 0.94) and `BigQueryFraudShieldRepo` (`USE_MOCK_BQ=false`, ADC auth, parameterised queries).
- Analyst decisions are append-only in `fraudshield.case_decisions` (created on first use); the API returns the latest decision per case.
- `app/routers/fraudshield.py` is the frontend contract, at root and mirrored at `/api/fs/*`. CORS from `CORS_ORIGINS`; optional `X-API-Key` when `API_KEY` is set.

| Method | Path | Notes |
|---|---|---|
| GET | /metrics | KPI cards |
| GET | /transactions?limit=50 | live feed, newest first; never returns label_is_fraud |
| GET | /cases?status=OPEN | queue sorted by risk desc |
| GET | /cases/{case_id} | detail incl. ai_summary (null until Phase B) |
| POST | /cases/{case_id}/decision | APPROVED / REJECTED / ESCALATED; 409 if already final |
| GET | /rings | customers, devices, accounts linked to held activity |
| POST | /cases/{case_id}/chat | 501 until Phase B |

## Original planned layout
```
app/
  main.py          # FastAPI app; serves static dashboard + /api
  config.py        # settings from env (.env)
  routers/         # fraud, documents, compliance, twin, copilot
  services/
    ai/            # AIProvider interface: MockAI, GeminiAI
    fraud.py, underwriting.py, aml.py, twin.py
  data/mock_data.py
static/index.html
tests/
requirements.txt, .env.example, Dockerfile
```

## Local vs Google Cloud mapping
| Concern | Local | Google Cloud |
|---|---|---|
| API runtime | uvicorn | Cloud Run |
| Operational DB | SQLite / mock | Cloud SQL Postgres (or AlloyDB) |
| Analytics | in-memory mock transactions | BigQuery |
| Event stream | direct function call | Pub/Sub |
| Document parsing | mock extraction | Document AI |
| Policy RAG | in-memory corpus | Vertex AI Search |
| LLM | Mock / Gemini (AI Studio key) | Gemini on Vertex AI |
| Secrets | `.env` | Secret Manager |

## Existing API endpoints
- `GET /api/health`
- `POST /api/transactions/simulate`
- `GET /api/documents/analyze/{filename}`
- `GET /api/compliance/sar/{case_id}`
- `GET /api/copilot/recommendations/{customer_id}`
