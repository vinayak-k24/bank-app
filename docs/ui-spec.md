# UI Specification — FinGuard 360

## 1. Look & shared navigation shell

### Visual style
Clean, light-mode enterprise look: bright white background with soft gray rounded cards.

| Color | Use only for |
|---|---|
| Blue | Primary action buttons |
| Green | Verified / safe states |
| Amber | Warnings |
| Red | Critical fraud or document mismatches |
| Purple | **Only** AI predictions and Gemini insights |

### Top bar (fixed)
- **Left:** FinGuard 360 logo.
- **Center:** 5 page tabs: Command Center · Live Payments & Scam Guard · Loan & Document Desk · Compliance & AML Studio · Personal Financial Coach.
- **Right:** Live Persona Switcher with Aarav Sharma (`CUST-101`), Apex Manufacturing SME (`SME-202`) and AML Case #AM-89412 (`AML-303`).

### Copilot
- Floating bottom-right button: **✨ FinGuard Copilot**.
- Opens a context-aware Gemini chat drawer on any page, for questions and one-click actions.

## 2. Pages

### Page 1: Command Center (Home)
**Shows**
- Hero greeting ("Good Morning, Alex") and a Gemini Morning Briefing card
- 4 KPI cards: Transactions Monitored, Fraud Blocked, Loans Pending, Open AML Cases
- Top 3 AI Recommended Action cards
- Risk Exposure vs. AI Savings area chart

**Interactions → result**
- "🔊 Listen to Briefing" → the browser reads the Gemini executive summary aloud (Web Speech API).
- Click a KPI card → jump to the related page.
- "Execute Action" on a recommendation → either jumps to the scenario page (2, 3 or 4) or resolves the alert in place. Resolving updates the KPI counters and adds a green intervention marker on the savings chart.

### Page 2: Live Payments & Scam Guard
**Shows**
- Payment simulator form: Recipient, Amount, Device/Location toggle
- Live incoming transaction stream with a 0–100% Vertex AI risk bar
- Multimodal scam scanner: a dropzone for invoices and screenshots

**Interactions → result**
- Enter $48,500 from "New Device" and click "Send Live Payment" → Pub/Sub streams the payment to the top of the feed. The risk bar animates to **95% High Risk (Red)** and the transfer goes on hold.
- "Scan Suspicious Invoice", or drop an invoice image/PDF → Gemini Vision highlights the spoofed bank account number and fake sender domain, then shows **"Block Scam"** and **"Verify via OTP"** buttons.

### Page 3: Loan & Document Desk
**Shows**
- 4-step progress stepper: Upload → Document AI Parse → Ledger Check → Decision
- PDF uploader with 2 quick-test files (clean vs. tampered)
- Split viewer: PDF preview on the left, extracted JSON fields in the middle, BigQuery match verdict on the right

**Interactions → result**
- "Upload Clean Bank Statement" (or drag a PDF) → Document AI animates field extraction in about 1 second. The PDF shows $14,250/mo, BigQuery shows $14,250/mo, the verdict turns **Green**, and a **$45,000 Instant Pre-Approval** card unlocks.
- "Upload Tampered Bank Statement" → a **Red Discrepancy Alert** flashes: the PDF says $18,500/mo but BigQuery says $12,400/mo. It cites UW-104 via Vertex AI Search, and the action button changes to **"Request Tax/GST Proof"**.
- Loan Term Slider (12–36 months) on an approved offer → the repayment terms recalculate.

### Page 4: Compliance & AML Studio
**Shows**
- Interactive 4-account network map (left)
- Matched RBI & FATF policy cards with confidence scores (middle)
- Rich-text SAR editor (right)

**Interactions → result**
- Select Case #AM-89412 and click "Trace Money Flow" → animated red arrows trace **$1.2M** moving in a circular loop across 4 shell accounts (queried from BigQuery).
- "✨ Auto-Draft SAR with Gemini" → Vertex AI Search highlights the broken rules (RBI KYC Sec 24(a), FATF Red Flag 3.1). Gemini streams a structured SAR into the editor.
- "Freeze Accounts & Submit SAR" → 1-click officer sign-off. This is the human approval step.

### Page 5: Personal Financial Coach
**Shows**
- Smart wallet balance card
- 30-day cash-flow forecast chart: a **Blue** actual line and a **Purple** Vertex AI prediction line
- "What-If" slider for a big expense or delayed invoice
- 2 personalized product cards

**Interactions → result**
- Drag the What-If slider → the purple forecast line redraws live and flags the exact date the balance dips low.
- "Check Eligibility & Terms" → Vertex AI Search and Gemini open a personalized explanation of how the pre-qualified **6.45% Invoice Credit Line** bridges the 12-day gap with zero overdraft fees.

## 3. Shared real-time state
- **Persona switch** updates the active data on all 5 pages without a page reload. Demo path: Aarav (retail) → Apex Mfg (SME loan) → #AM-89412 (AML).
- **Cross-page effects on the Command Center:**
  - blocking a scam (page 2), pausing a tampered loan (page 3) or submitting a SAR (page 4) decreases **Open Alerts** and increases **Projected Savings** automatically.
- **Context-aware Copilot:** the suggested one-click questions change per page. For example, "Why was Apex Mfg's bank statement flagged?" on page 3, or "Summarize RBI KYC Sec 24(a)" on page 4.

## Implementation notes
- A single-page app with a client-side store for the active persona, KPIs, alerts and savings. The backend is the source of truth through `/api/state`.
- Every "live" effect (scoring, extraction, SAR streaming) calls the FastAPI backend. Mock mode returns the same shapes with simulated latency.
- Gemini SAR and Copilot output are streamed (SSE) for the typing effect.
- Demo numbers above are fixed in mock data and must stay consistent across pages.
