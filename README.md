# FinGuard 360

An AI risk, document and financial copilot for banks, lenders and insurers. FinGuard links the **customer experience** and the **bank officer's workflow** around one shared brain, built on Google Cloud.

## The problem

Fraud checks, document verification, compliance and customer guidance run in separate silos today. That causes four problems:

1. **Fraud is caught too late, or the wrong people are blocked.** Rules look only at amount and location, so they block real purchases and miss invoice scams and social-engineering transfers.
2. **Documents are checked by hand.** Staff spend days reading bank statements, IDs, tax filings and claim bills to spot doctored numbers.
3. **Investigations and compliance reports are manual.** One suspicious-activity case can take hours of log searching and reading RBI and FATF rulebooks.
4. **Customers only see the past.** People and small businesses aren't warned about upcoming cash shortages, or offered the right credit or savings product in time.

## What FinGuard does

| Who it helps | What it does |
|---|---|
| Customers and small businesses | Warns about scam invoices, pauses one risky transfer and confirms it over chat (the account is never frozen), and forecasts 30-day cash dips with a matching product |
| Loan and claims officers | Reads statements and claim invoices in seconds, checks them against the customer's real transactions, and gives an instant risk score and decision |
| Fraud and compliance teams | Detects money moving in circles, cites the exact RBI/FATF rule, and drafts the suspicious activity report (SAR) for officer sign-off |

The app has five pages (Command Center, Live Payments & Scam Guard, Loan Claim & Document Desk, Compliance & AML Studio, Personal Financial Coach), a persona switcher, and a floating **FinGuard Copilot**.

## Google Cloud services

| Service | Purpose in FinGuard | Status |
|---|---|---|
| **Cloud Run** | Hosts the FastAPI backend and web UI as one serverless container | Planned |
| **Gemini on Vertex AI** | Explains decisions, reads invoices (vision), summarizes document mismatches, drafts SARs, powers the Copilot | Live path built (AI Studio key or Vertex); mock by default |
| **Pub/Sub** | Streams live payment events into fraud scoring | In-memory stand-in |
| **BigQuery** | Transaction history ledger, 30-day income checks, AML money-flow graph, cash-flow forecasts | In-memory stand-in; data in `data/` |
| **Vertex AI (predictive ML)** | Real-time fraud scoring model (trained with BigQuery ML) and cash-flow forecasting | Rule-based stand-in |
| **Document AI** | Extracts fields from statements, IDs, tax returns, invoices and claim forms | Stand-in; extractions in `data/` |
| **Vertex AI Search (Agent Builder)** | Searches RBI/FATF rules, underwriting policy and the product catalog to ground AI answers | Keyword stand-in |
| **Cloud SQL / AlloyDB** | Accounts, verified vendors, loans, claims and compliance cases | In-memory stand-in; seed SQL in `data/` |
| **Secret Manager** | Stores API keys and database passwords | Planned |
| **Cloud Storage** | Holds uploaded documents and the dataset for import | Planned |
| **Vertex AI Agent Engine** | Managed runtime for the ADK agents (sessions, memory, scaling) | Planned |
| **Vertex AI RAG Engine** | Semantic retrieval over RBI/FATF rules, underwriting policy and the product catalog, with citations | Planned (replaces the keyword stand-in) |
| **Model Armor** | Screens prompts, uploaded documents and responses for prompt injection, jailbreaks and data leaks | Planned |
| **Sensitive Data Protection (Cloud DLP)** | Detects and masks account numbers, PAN, Aadhaar and phone numbers before data reaches Gemini | Planned |
| **Gemini Live API** | Real-time voice conversation with the FinGuard Copilot | Planned |
| **Cloud Translation** | Customer warnings and coaching in Hindi, Tamil and other Indian languages | Planned |

Every service sits behind an interface with a mock and a live version, so the app runs fully offline and switches to Google Cloud by configuration.

## AI agents (planned)

Gemini will run as a **multi-agent system with tool calling**, not a chat box. A **FinGuard Orchestrator** routes work to four agents, one per page:

- **FraudShieldAgent:** scores payments, checks vendors against verified accounts, scans invoices.
- **UnderwritingAgent:** extracts document fields, verifies income against the ledger, applies underwriting rules.
- **ComplianceSARAgent:** traces AML money loops, inspects trade invoices, retrieves RBI/FATF rules, drafts SARs.
- **FinancialCoachAgent:** reads cash-flow forecasts, runs what-if scenarios, matches products.

Each page shows a live **Agent Execution Trace** of every tool the agent calls. Details: [`docs/agents-plan.md`](docs/agents-plan.md). Agent code goes in `app/agents/`.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8080
```

Open http://127.0.0.1:8080. Run the tests with `.\.venv\Scripts\python.exe -m pytest -q`.

`requirements.txt` lists direct dependencies with compatible version ranges. `requirements-lock.txt` pins every package to the exact versions the app is tested with; install it with `pip install -r requirements-lock.txt` for a reproducible setup.

To use real Gemini, copy `.env.example` to `.env`, set `USE_MOCK_AI=false`, and set either `GEMINI_API_KEY` or `USE_VERTEX=true` with `GCP_PROJECT_ID`.

## Project layout

```
app/            FastAPI backend (routes, services, mock data, agents/)
static/         Web UI (HTML, CSS, JS; no external CDN)
data/           Demo dataset: AlloyDB seed, BigQuery CSVs, Document AI extractions, Pub/Sub stream, RAG chunks
docs/           Requirements, UI spec, architecture, AI services, agents plan, decision log
tests/          API tests
AGENTS.md       Instructions for coding agents (Cortex Code and others)
MEMORY.md       Key project facts and decisions
```

## References

- **Google Antigravity SDK (Python):** Python SDK for building Gemini-powered agents with custom tools, MCP, hooks and policies. https://github.com/google-antigravity/antigravity-sdk-python (`pip install google-antigravity`)
- **Google Agent Development Kit (ADK):** framework for multi-agent systems with tool calling; the chosen framework for the FinGuard agents. https://google.github.io/adk-docs/ (`pip install google-adk`)
- **Google Gen AI SDK for Python:** Gemini API and Vertex AI client used by the backend today. https://github.com/googleapis/python-genai (`pip install google-genai`)
- **Dataset guide:** [`data/readme_data.md`](data/readme_data.md), covering what each file is and how to load it into Google Cloud.
