# Multi-Agent Plan: FinGuard Orchestrator + 4 Sub-Agents

Status: **Planned** (not implemented). Added 2026-10-14.

Goal: use Gemini as a **multi-agent system with tool calling** rather than a chat box. Specialized agents call the data, ML and policy-search tools step by step, take actions, and show their reasoning in the UI.

## 1. Architecture

```
                 FinGuard Orchestrator (supervisor)
        routes each request to one sub-agent, merges the answer
   ┌───────────────┬──────────────────┬──────────────────┬───────────────────┐
FraudShieldAgent  UnderwritingAgent  ComplianceSARAgent  FinancialCoachAgent
  (Page 2)          (Page 3)           (Page 4)           (Page 5 + Copilot)
```

Each agent = system instruction + a fixed set of Python **tools**. A tool reads `./data/` in local mode, or the matching Google Cloud service in cloud mode, behind the same function signature.

## 2. Agents, tools and workflows

### FraudShieldAgent (Page 2: Payments & Scam Guard)
Goal: intercept suspicious transfers and spoofed vendor invoices in real time.

| Tool | Local source (`./data/`) | Cloud source |
|---|---|---|
| `score_tx_anomaly(tx)` | `finguard_bigquery_transactions.csv` features + scoring rules | Vertex AI endpoint `finguard_fraud_anomaly_detector` (BigQuery ML) + Pub/Sub |
| `check_whitelisted_vendor(customer_id, vendor, account_last4, domain)` | `verified_beneficiaries` in `alloydb_seed_schema_and_data.sql` / structured JSON | AlloyDB `verified_beneficiaries` |
| `scan_invoice_image(doc_id or file)` | `document_ai_all_12_extractions.json` (DOC-07 spoofed, DOC-06 valid, DOC-10 SMS lure) | Gemini Vision |
| `hold_or_approve_tx(tx_id, decision)` | in-memory state | AlloyDB |

Workflow: a $14,250 invoice payment arrives → `scan_invoice_image` reads account …8841 and `@netcorp-pay.co` → `check_whitelisted_vendor` finds the real NetCorp is …2209 at `netcorp.com` (VEND-901) → `hold_or_approve_tx("BLOCKED")` → the customer is alerted.

### UnderwritingAgent (Page 3: Loan, Claim & Document Desk)
Goal: verify loan PDFs and insurance claims against real bank records.

| Tool | Local source | Cloud source |
|---|---|---|
| `extract_pdf_fields(doc_id)` | `document_ai_all_12_extractions.json` (DOC-01..05, 08, 09, 12) | Document AI |
| `verify_ledger_income(customer_id)` | `finguard_bigquery_transactions.csv` (90-day inflows) | BigQuery `transactions_history` |
| `check_field_inspection(doc_id)` | DOC-12 (Apex handwritten field inspection) | Document AI |
| `lookup_underwriting_rule(query)` | RAG chunk `UW-POLICY-104` (KB-03) | Vertex AI Search |

Workflow: `extract_pdf_fields("DOC-02")` → $18,500/mo declared, with a tamper flag → `verify_ledger_income("SME-202")` → $12,400/mo actual (+49.2%) → `lookup_underwriting_rule()` → clause UW-104.2 (>15% variance hold) → loan #LN-4092 set to `HOLD_DISCREPANCY_ALERT`, plus an audit memo.

### ComplianceSARAgent (Page 4: Compliance & AML Studio)
Goal: investigate circular money loops and draft SARs.

| Tool | Local source | Cloud source |
|---|---|---|
| `query_aml_ring_edges(case_id)` | `bigquery_aml_network_edges.csv` | BigQuery `aml_network_edges` |
| `inspect_trade_invoices(doc_id)` | DOC-11 (faxed shell trade invoices, customs stamp check) | Document AI |
| `search_rbi_fatf_rules(query)` | RAG chunks `RBI-KYC-24A`, `RBI-KYC-16C`, `FATF-REDFLAG-3.1` (KB-01/KB-02) | Vertex AI Search |
| `save_sar_report(case_id, text)` | in-memory state | AlloyDB `compliance_cases` |

Workflow: `query_aml_ring_edges("AM-89412")` → $1.2M across 4 shell accounts in ~68h → `inspect_trade_invoices("DOC-11")` → no customs stamps → `search_rbi_fatf_rules()` → RBI KYC 24(a) and FATF 3.1 → draft and save the SAR. **Human sign-off is still required before filing.**

### FinancialCoachAgent (Page 5 + floating Copilot)
Goal: predict cash-flow dips and match products.

| Tool | Local source | Cloud source |
|---|---|---|
| `get_30d_cashflow_series(customer_id)` | `bigquery_cashflow_30d_forecasts.csv` | BigQuery `cashflow_30d_forecasts` / Vertex AI Forecasting |
| `simulate_what_if_expense(customer_id, delay_days, expense_usd)` | Python calculator | same |
| `match_product_catalog(customer_id, need)` | RAG chunk `PROD-CATALOG-2026` (KB-04) | Vertex AI Search |

Workflow: `get_30d_cashflow_series("CUST-101")` → -$4,200 dip on Oct 26 → `match_product_catalog()` → PROD-INV-FIN-01 ($45K @ 6.45% APR) → explain in plain English.

### FinGuard Orchestrator (Copilot drawer)
Classifies each question, delegates to one or more sub-agents, and returns the combined answer **plus the tool trace**. Example: "Check why Apex Mfg's loan was blocked and whether their field inspection passed" → UnderwritingAgent (`extract_pdf_fields`, `verify_ledger_income`, `check_field_inspection`, `lookup_underwriting_rule`).

## 3. Implementation options on Google Cloud
1. **Code-first (primary):** Google ADK agents inside the FastAPI app. Tools are plain Python functions; local mode reads `./data/`, cloud mode queries BigQuery and AlloyDB.
2. **Vertex AI Agent Engine (hosting):** deploy the ADK agents to Agent Engine for managed sessions, memory and scaling. The FastAPI app on Cloud Run calls them; locally they run in-process.
3. **Vertex AI RAG Engine (grounding):** index the RAG chunks (RBI-KYC-24A, RBI-KYC-16C, FATF-REDFLAG-3.1, UW-POLICY-104, PROD-CATALOG-2026) as corpora KB-01..KB-04. `lookup_underwriting_rule`, `search_rbi_fatf_rules` and `match_product_catalog` call RAG Engine retrieval and return chunk IDs as citations. This replaces the current keyword search in `app/services/rag.py`. Vertex AI Search (Agent Builder) stays an alternative.

### Safety layer (applies to every agent)
- **Sensitive Data Protection (Cloud DLP):** de-identify account numbers, PAN, Aadhaar, phone numbers and emails in tool outputs and documents before they go into a Gemini prompt. Keep the real values server-side for the deterministic tools.
- **Model Armor:** screen (a) user prompts in the Copilot, (b) text extracted from uploaded invoices and PDFs, which could carry prompt injection, and (c) model responses. Blocked content stops the run and appears in the trace as a red "Model Armor blocked" step.
- Both run as before/after callbacks on the ADK agents, so the trace shows them, e.g. `🛡️ Model Armor → prompt clean` and `🔒 DLP → masked 2 account numbers`.

### Voice and language (Copilot and customer pages)
- **Gemini Live API:** a mic button in the Copilot drawer opens a real-time voice session with the Orchestrator. The same tools run and the trace updates while it speaks.
- **Cloud Translation:** translate customer-facing explanations (payment holds, scam warnings, coaching) into the customer's preferred language. Officer-facing text and SARs stay in English. Amounts and IDs are left untranslated.

## 4. UI: Agent Execution Trace
- Every page that runs an agent (Pages 2–5 and the Copilot drawer) shows a live **Agent Execution Trace**: one row per tool call, lighting up as it runs, showing the tool name, arguments, a short result, and the final action.
  ```
  🔍 UnderwritingAgent → extract_pdf_fields(DOC-02): $18,500/mo + font tamper flag
  📊 UnderwritingAgent → verify_ledger_income(SME-202): BigQuery $12,400/mo (+49.2%)
  📖 UnderwritingAgent → lookup_underwriting_rule(): UW-104.2 (>15% variance hold)
  🛑 UnderwritingAgent → Final action: Loan #LN-4092 → HOLD_DISCREPANCY_ALERT
  ```
- Steps are streamed (SSE) from the backend as they happen, not replayed after the fact.

## 5. Guardrails (carry over from AGENTS.md)
- Decisions and amounts come from deterministic tools. The LLM chooses which tools to call and explains the result; it never invents numbers.
- Customer accounts are never frozen for a single payment; SAR filing and account freezes need officer sign-off.
- Every tool call is written to the audit log.
- Mock mode replays a scripted tool sequence with the same trace format, so the demo works without keys.

## 6. Prerequisites and open items
- [ ] **Switch the app's data source to `./data/`.** Today the app uses hand-written `app/data/mock_data.py` and does not read `./data/` at all. The tools above depend on these files.
- [ ] **Reconcile numbers** between `./data/` and the current app (pick one source of truth):
  - AML ring: `./data/` has one $1.2M amount hopping 4 times with $5K fees over ~68h (Zenith Imports, Nova Logistics, Pacific Exim, Meridian Ventures); the app has 4 × $300K over 47.3h with generic names.
  - Aarav's forecast: `./data/` shows a baseline balance near $128K and a -$4,200 dip on Oct 26; the app uses a $6,850 wallet with a 12-day gap starting Oct 24.
  - Insurance claims: `./data/` has Priya Nair (DOC-08 repair estimate, DOC-09 medical claim); the app invented CL-5530 and CL-7741.
  - Policy IDs: `./data/` has `RBI-KYC-16C` and `PROD-CATALOG-2026`; the app has `CLM-POL-12` and two separate product IDs.
- [ ] Confirm KB-01..KB-04 mapping: KB-01 = RBI, KB-02 = FATF, KB-03 = underwriting, KB-04 = product catalog (assumed from the plan).
- [x] Choose ADK vs. plain `google-genai` function calling: **Google ADK** (`google-adk` 2.12.0 installed in `.venv`, added to requirements.txt on 2026-10-14).
- [ ] Verify availability, quotas and package names for Agent Engine, RAG Engine, Model Armor, Sensitive Data Protection, Gemini Live API and Cloud Translation in the target GCP project and region (chosen 2026-10-14; not verified against current docs).
- [ ] Decide whether both Gemini Live API and Cloud Translation are in scope, or only one.
- [ ] The UI redesign direction (risk ledger desk / money-flow river / case dossier) is still undecided, and the trace component should be designed with it.

## 7. Planned code layout (`app/agents/`)
```
app/agents/
  __init__.py
  base.py            # Agent, Tool, TraceStep types; run loop (Gemini function calling or mock replay)
  tools/             # one module per data source; local (./data) and cloud implementations
  fraud_shield.py
  underwriting.py
  compliance_sar.py
  financial_coach.py
  orchestrator.py    # routing + merged answer
```
Planned API: `POST /api/agents/{agent}/run` and `POST /api/agents/orchestrator/chat`, both streaming trace steps.
