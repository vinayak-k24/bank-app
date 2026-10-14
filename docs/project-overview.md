# Project Overview — FinGuard

## Goal
FinGuard is an end-to-end AI risk, document and financial copilot. It connects the **customer experience** and the **bank officer workflow** around one shared brain, built on Google Cloud.

## Problem statement (what is broken today)
In banking, lending and insurance, fraud checks, document verification, compliance and customer guidance run in separate silos. That causes four pain points:

1. **Fraud is caught too late, or the wrong people are blocked.** Legacy systems look only at transaction amount and location. They block legitimate purchases but miss invoice scams and social-engineering transfers, where a customer is tricked into sending money.
2. **Manual document verification.** Staff spend days reading PDF bank statements, IDs, tax filings and claim bills by hand to check whether the numbers are genuine or doctored.
3. **Manual investigations and compliance reports.** Compliance officers spend hours searching transaction logs and dense rulebooks (RBI, FATF) to document a single case.
4. **Backward-looking customer views.** Customers see only past balances, not future risks. Individuals and small businesses get blindsided by cash shortages instead of being warned early and offered the right credit or savings option.

## Solution: who it helps
| Persona | What FinGuard does | Google Cloud behind it |
|---|---|---|
| **Everyday customers & small businesses** | Warns when an invoice or payment request looks like a scam. Pauses unusual transfers and confirms via chat instead of freezing the account. Forecasts 30-day cash-flow dips and suggests tailored credit or savings products. | Pub/Sub streams live payments. BigQuery + Vertex AI score anomalies and forecast cash flow. Vertex AI Search finds matching products. Gemini explains in plain English. |
| **Loan & insurance claims officers** | Reads uploaded PDF statements, IDs and claim invoices in seconds. Compares the PDF numbers against the customer's real transaction history to catch fake or inflated claims. Gives an instant risk score. | Document AI extracts fields. Cloud SQL / AlloyDB + BigQuery cross-check account history. Gemini summarizes mismatches. |
| **Fraud & compliance teams** | Flags suspicious money movement across accounts. Pulls the exact applicable regulatory rule. Drafts the Suspicious Activity Report (SAR), ready for sign-off. | BigQuery spots the pattern. Vertex AI Search retrieves the RBI/FATF clause. Gemini writes the report. Cloud Run hosts the app. |

## Why it fits together: one customer lifecycle
FinGuard is one product, not seven unrelated tools. Everything follows the customer's lifecycle:
1. **Day-to-day banking:** keeps daily payments safe from scams and helps manage cash flow.
2. **Applying for a loan or claim:** reads documents and scores risk instantly.
3. **Back-office oversight:** when the AI catches a fake document or suspicious transfer, the officer gets a ready-made investigation and compliance report.

## Modules (dashboard tabs)
| Module | Persona | Purpose |
|---|---|---|
| Command Center | Officers / execs | Daily risk, compliance and treasury briefing; top alerts |
| Personal Finance / Financial Twin | Customers & SMEs | Cash-flow forecast, proactive product offers |
| Fraud & Anomaly | Customers + fraud team | Real-time scoring, scam warnings, chat-based step-up |
| Document AI | Loan/claims officers | Parse statements, invoices, IDs, claim bills; detect tampering |
| Underwriting & Risk | Loan/claims officers | Reconcile declared vs. ledger figures; risk score and decision |
| Compliance & AML | Compliance team | Suspicious flow detection; SAR drafting with citations |
| Executive | Leadership | Business impact KPIs |
| Copilot / Insights | All | Conversational AI over all of the above |
| Admin | Admin | Settings, users |

## Success criteria
- TBD (e.g., false-positive reduction, document review time, SAR drafting time, demo flows working end to end)
