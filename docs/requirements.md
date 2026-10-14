# Requirements & Business Rules

## Existing rules (from current code)
- Fraud (implemented v1): score = 0.10 base; +0.30 new device; +0.25 unusual location; +min(0.20, velocity*0.04) if velocity > 2.0; +0.10 new payee; capped 0.98. >= 0.75 -> `HELD_FOR_CONFIRMATION` (account never frozen); >= 0.40 -> `APPROVED_WITH_WARNING`; else `APPROVED`.
- Velocity ratio = amount / (avg monthly deposits / 4).
- Underwriting (UW-104): declared vs ledger deposits variance > 15% -> `MANUAL_STEP_UP_REQUIRED`; else `INSTANT_PRE_APPROVED` up to $45,000 @ 6.45% APR.
- AML: closed-loop transfers across >= 3 entities within 72h -> flag (FATF 3.1, RBI KYC 24(a)); draft SAR.
- Financial Twin: negative 30-day cash-flow forecast -> offer invoice financing line (PROD-INV-FIN-01).

## Functional requirements (from problem statement)

### R1. Customer payment protection (customers & SMEs)
- R1.1 Score each payment using behavior, not just amount and location: device trust, velocity vs. history, new payee, payee account change, sender domain age.
- R1.2 Detect invoice and payment-request scams. Example: invoice routing account differs from the historically verified account; vendor domain registered recently.
- R1.3 Detect social-engineering transfers (customer tricked into sending money). Example: unusual payee plus urgency and an atypical amount.
- R1.4 On high risk, **pause the single transfer and confirm via chat**. Do not freeze the account.
- R1.5 Gemini explains every warning in plain English.

### R2. Cash-flow forecast & guidance (customers & SMEs)
- R2.1 Forecast the 30-day balance and flag upcoming dips.
- R2.2 Recommend matching credit or savings products retrieved from the product catalog (RAG), with grounded terms.

### R3. Document & risk checks (loan & claims officers)
- R3.1 Extract fields from bank statements, IDs, tax filings and claim invoices/bills.
- R3.2 Cross-check extracted numbers against the customer's real transaction history; flag variance (UW-104: >15%).
- R3.3 Flag tampering signals (PDF text-layer edits, font/kerning anomalies, low OCR confidence).
- R3.4 Return an instant risk score, a verdict, and a Gemini mismatch summary.
- R3.5 Cover both loans and insurance claims (claim bills vs. history/policy).

### R4. Compliance & AML (fraud & compliance teams)
- R4.1 Detect suspicious multi-account flows (circular/round-tripping, layering, rapid velocity).
- R4.2 Retrieve the exact applicable RBI/FATF clause with citation.
- R4.3 Draft a SAR in standard sections, ready for officer sign-off. Human approval is required before filing.

### R5. Shared brain & handoff
- R5.1 One shared customer profile and event history across all modules.
- R5.2 Fraud and document findings automatically create a case for the back office, with investigation summary and draft report.
- R5.3 Copilot answers questions across customer, document and case data.

### R6. Multi-agent tool calling (PLANNED, see docs/agents-plan.md)
- R6.1 A FinGuard Orchestrator routes requests to FraudShieldAgent, UnderwritingAgent, ComplianceSARAgent and FinancialCoachAgent.
- R6.2 Each agent calls Python tools (data, ML scoring, policy search, actions) step by step instead of answering from text alone.
- R6.3 Every page that runs an agent, and the Copilot drawer, shows a live Agent Execution Trace of tool calls and the final action.
- R6.4 Tools read `./data/` locally and Google Cloud services in cloud mode, behind the same signatures.

## Non-functional
- Runs locally in mock mode with no keys; same code runs on Google Cloud.
- Explainable decisions; every AI output has an audit trail.
- Synthetic data only; mask PII sent to LLMs.
