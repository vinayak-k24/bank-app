# FinGuard 360 — Agent Instructions

AI-driven banking risk, fraud & financial command center. Build locally first, deploy to Google Cloud later.

## Stack
- Language: Python 3.13 (local), FastAPI + Uvicorn, Pydantic
- AI: Gemini via `google-genai` SDK (AI Studio key locally -> Vertex AI on GCP via config only)
- Target cloud: Google Cloud (Cloud Run, Cloud SQL Postgres, BigQuery, Pub/Sub, Document AI, Vertex AI Search, Secret Manager)
- Frontend: existing static dashboard `finguard_360_command_center.html` (to be wired to the API with fetch)

## Rules
- Every external service (Gemini, BigQuery, Document AI, Pub/Sub, ...) sits behind an interface with a **mock** and a **live** implementation. Mock is the default (`USE_MOCK_AI=true`) so the app runs offline with zero keys.
- Never hardcode secrets. Read from env / `.env` (gitignored); on GCP use Secret Manager.
- Money logic is deterministic Python, never LLM output. LLMs explain, summarize, draft — they do not decide amounts or approvals alone.
- Ground AI outputs in policy text (RAG corpus) and cite `doc_id`s.
- Keep original files `finguard_backend_and_mock_data.py` and `finguard_360_command_center.html` until migration is confirmed.
- Use mock/synthetic data only; no real customer PII.
- Shell is Windows PowerShell.

## Commands (PowerShell, from D:\bank-app)
- Setup: `python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt`
- Run app: `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8080` then open http://127.0.0.1:8080
- Tests: `.\.venv\Scripts\python.exe -m pytest -q` (must stay green; demo numbers are asserted)
- Live Gemini: copy `.env.example` to `.env`, set `USE_MOCK_AI=false` and `GEMINI_API_KEY` (or `USE_VERTEX=true` + `GCP_PROJECT_ID`)
- Legacy prototype (reference only): `finguard_backend_and_mock_data.py`, `finguard_360_command_center.html`

## Code map
- `app/main.py` routes · `app/config.py` settings · `app/data/mock_data.py` demo data
- `app/services/`: `ai.py` (mock/Gemini provider), `state.py` (shared KPIs/alerts/cases), `fraud.py`, `underwriting.py`, `aml.py`, `coach.py`, `rag.py`, `command.py` (briefing, actions, copilot), `fraudshield.py` (teammate's BigQuery `fraudshield` dataset: mock + BigQuery repos, scorer formula)
- `app/routers/fraudshield.py` — FraudShield frontend contract (`/metrics`, `/transactions`, `/cases`, `/rings`, also `/api/fs/*`). Treat its field names as a contract with the teammate; flag changes. `USE_MOCK_BQ=false` + `BQ_PROJECT_ID` + ADC for live.
- `static/`: `index.html`, `styles.css`, `charts.js` (SVG, no CDN), `app.js` (SPA; escape all API text with `esc()`, no inline handlers)

## Reference docs (read when relevant)
- `README.md` — project summary, Google Cloud services and their purpose, references (Antigravity SDK, ADK, Gen AI SDK)
- `MEMORY.md` — key facts & decisions
- `docs/project-overview.md` — goals, users, modules
- `docs/requirements.md` — features & business rules
- `docs/ui-spec.md` — UI look, 5 pages, interactions, shared state (follow the color rules strictly)
- `docs/architecture.md` — components, data flow, local vs GCP mapping
- `docs/ai-services.md` — AI service usage & prompt guidelines
- `docs/agents-plan.md` — **planned** multi-agent system (Orchestrator + 4 tool-calling agents, execution trace UI); code goes in `app/agents/`
- `data/readme_data.md` — the real demo dataset in `./data/` (AlloyDB seed, BigQuery CSVs, Document AI DOC-01..12, Pub/Sub stream, RAG chunks). Not yet wired into the app.
- `docs/decisions.md` — dated decision log (append new decisions here)
