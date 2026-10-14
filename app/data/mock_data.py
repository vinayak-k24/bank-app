"""Deterministic demo data shared by every page. Keep the numbers in sync with docs/ui-spec.md."""

from __future__ import annotations

from typing import Any

PERSONAS: dict[str, dict[str, Any]] = {
    "CUST-101": {
        "customer_id": "CUST-101",
        "name": "Aarav Sharma",
        "short": "Aarav Sharma",
        "segment": "Retail & Freelance",
        "risk_tier": "Low",
        "kyc_status": "Verified",
        "avg_monthly_deposits_usd": 14250.00,  # ledger truth (BigQuery)
        "known_payees": ["Metro Utilities", "AWS Cloud", "Landlord - R. Mehta", "Payroll Batch"],
        "default_document": "clean",
        "wallet": {
            "balance_usd": 6850.00,
            "low_threshold_usd": 1000.00,
            "daily_spend_usd": 380.00,
            "fixed_outflows": [{"day": 3, "label": "Rent", "amount_usd": 2200.00}],
            "pending_inflow": {"day": 22, "label": "Client invoice #INV-2291", "amount_usd": 9500.00},
        },
    },
    "SME-202": {
        "customer_id": "SME-202",
        "name": "Apex Manufacturing Pvt Ltd",
        "short": "Apex Manufacturing SME",
        "segment": "SME Commercial Lending",
        "risk_tier": "Medium-Watch",
        "kyc_status": "Verified",
        "avg_monthly_deposits_usd": 12400.00,
        "known_payees": ["NetCorp Supplies", "Global Freight", "Metro Utilities", "Payroll Batch"],
        "default_document": "tampered",
        "wallet": {
            "balance_usd": 18400.00,
            "low_threshold_usd": 5000.00,
            "daily_spend_usd": 610.00,
            "fixed_outflows": [{"day": 5, "label": "Payroll", "amount_usd": 6800.00}],
            "pending_inflow": {"day": 20, "label": "Distributor receivable", "amount_usd": 21000.00},
        },
    },
    "AML-303": {
        "customer_id": "AML-303",
        "name": "Shell Co. A (Case #AM-89412)",
        "short": "AML Case #AM-89412",
        "segment": "Cross-Border Treasury",
        "risk_tier": "Critical-AML",
        "kyc_status": "Enhanced Due Diligence Required",
        "avg_monthly_deposits_usd": 95000.00,
        "known_payees": ["Transit Account B"],
        "default_document": None,  # no loan application
        "wallet": None,  # under investigation: no customer coaching
    },
}

# Per-persona demo story: what each page preloads when this persona is active.
SCENARIOS: dict[str, dict[str, Any]] = {
    "CUST-101": {
        "banner": "Retail customer · freelancer with a pending client invoice",
        "story": "Aarav is being pushed to send $48,500 from an unknown device, has applied for credit, and faces a 12-day cash dip.",
        "payment": {"recipient": "Offshore Transit Ltd", "amount_usd": 48500.00, "new_device": True},
        "focus_recs": ["REC-SCAM", "REC-LOAN", "REC-AML", "REC-GROWTH"],
        "document_hint": "Aarav applied for a $45,000 credit line and filed a gadget damage claim.",
        "default_claim": "claim_clean",
        "aml_note": "No suspicious network activity for Aarav. Showing the bank's open case #AM-89412.",
    },
    "SME-202": {
        "banner": "SME borrower · loan application and vendor payments",
        "story": "Apex received a look-alike vendor invoice and submitted a bank statement with inflated deposits.",
        "payment": {"recipient": "NetCorp Billing LLC", "amount_usd": 14250.00, "new_device": False},
        "focus_recs": ["REC-LOAN", "REC-SCAM", "REC-GROWTH", "REC-AML"],
        "document_hint": "Apex Manufacturing submitted a statement for a working-capital loan and a machinery claim.",
        "default_claim": "claim_inflated",
        "aml_note": "No suspicious network activity for Apex. Showing the bank's open case #AM-89412.",
    },
    "AML-303": {
        "banner": "Subject of AML case #AM-89412 · enhanced due diligence",
        "story": "Shell Co. A is the hub of a $1.2M circular loop across 4 accounts in 72 hours.",
        "payment": {"recipient": "Global Traders C", "amount_usd": 300000.00, "new_device": False},
        "focus_recs": ["REC-AML", "REC-SCAM", "REC-LOAN", "REC-GROWTH"],
        "document_hint": "No loan application on file. Accounts are under compliance review.",
        "aml_note": "Shell Co. A is the subject of this case.",
    },
}

# Payees tied to reported scams (from scam scans and fraud intel)
SCAM_PAYEES = {"NetCorp Billing LLC": "Account …8841 matches reported invoice scam INV-992"}

# Document AI extraction outputs (mock). Ledger truth comes from PERSONAS.
DOCUMENTS: dict[str, dict[str, Any]] = {
    "clean": {
        "filename": "Bank_Statement_Aarav_Clean.pdf",
        "processor_type": "BANK_STATEMENT_PROCESSOR",
        "customer_id": "CUST-101",
        "fields": {
            "account_holder": "Aarav Sharma",
            "account_number": "XXXX-XXXX-4471",
            "statement_period": "Jul 2026 - Sep 2026",
            "avg_monthly_deposits_usd": 14250.00,
            "ending_balance_usd": 128450.00,
            "ocr_confidence": 0.998,
        },
        "tamper_signals": [],
        "lines": [
            {"date": "2026-07-31", "desc": "Monthly credits total", "amount_usd": 14180.00},
            {"date": "2026-08-31", "desc": "Monthly credits total", "amount_usd": 14320.00},
            {"date": "2026-09-30", "desc": "Monthly credits total", "amount_usd": 14250.00},
            {"date": "2026-09-30", "desc": "3-month average deposits", "amount_usd": 14250.00, "summary": True},
        ],
    },
    "tampered": {
        "filename": "Bank_Statement_ApexMfg_Tampered.pdf",
        "processor_type": "BANK_STATEMENT_PROCESSOR",
        "customer_id": "SME-202",
        "fields": {
            "account_holder": "Apex Manufacturing Pvt Ltd",
            "account_number": "XXXX-XXXX-9032",
            "statement_period": "Jul 2026 - Sep 2026",
            "avg_monthly_deposits_usd": 18500.00,
            "ending_balance_usd": 84300.00,
            "ocr_confidence": 0.991,
        },
        "tamper_signals": [
            "Page 2 summary row has a modified PDF text layer (kerning mismatch)",
            "Summary total does not equal the sum of monthly rows",
        ],
        "lines": [
            {"date": "2026-07-31", "desc": "Monthly credits total", "amount_usd": 12350.00},
            {"date": "2026-08-31", "desc": "Monthly credits total", "amount_usd": 12480.00},
            {"date": "2026-09-30", "desc": "Monthly credits total", "amount_usd": 12370.00},
            {"date": "2026-09-30", "desc": "3-month average deposits", "amount_usd": 18500.00, "summary": True, "tampered": True},
        ],
    },
}

SCAM_INVOICE: dict[str, Any] = {
    "filename": "suspicious_invoice_992.pdf",
    "vendor_name": "NetCorp Billing LLC",
    "claimed_vendor": "NetCorp Supplies",
    "sender_email": "accounts@netcorp-pay.co",
    "sender_domain": "netcorp-pay.co",
    "domain_age_days": 4,
    "verified_domain": "netcorp.com",
    "invoice_number": "INV-992",
    "invoice_amount_usd": 14250.00,
    "routing_account_last4": "8841",
    "historical_verified_account_last4": "2209",
    "urgency_language": "Payment overdue - pay within 2 hours to avoid service suspension",
}

POLICIES: list[dict[str, Any]] = [
    {
        "doc_id": "RBI-KYC-24A",
        "category": "AML_REGULATION",
        "title": "RBI Master Direction on KYC - Sec 24(a): Complex & Circular Transactions",
        "clause": "Regulated entities must flag rapid circular movement of funds across multiple accounts lacking clear economic rationale and file an electronic Suspicious Transaction Report (STR/SAR).",
        "keywords": ["circular", "velocity", "rbi", "kyc", "24", "str", "sar", "loop"],
    },
    {
        "doc_id": "FATF-REDFLAG-3.1",
        "category": "AML_REGULATION",
        "title": "FATF Recommendation 10 & Red Flag Indicator 3.1: Shell Company Round-Tripping",
        "clause": "High-value funds transferred in a closed loop across 3 or more corporate entities within 72 hours indicate layering and beneficial-ownership obfuscation.",
        "keywords": ["fatf", "shell", "round-tripping", "loop", "layering", "72", "entities"],
    },
    {
        "doc_id": "UW-POLICY-104",
        "category": "UNDERWRITING_POLICY",
        "title": "FinGuard Underwriting Policy UW-104: Income Verification & Ledger Reconciliation",
        "clause": "When Document AI extracted deposits diverge from core ledger history by more than 15%, auto-approval must be paused pending Tax/GST/ITR proof.",
        "keywords": ["underwriting", "statement", "deposits", "variance", "ledger", "15", "gst", "tampered"],
    },
    {
        "doc_id": "FRAUD-POL-07",
        "category": "FRAUD_POLICY",
        "title": "Payment Protection Policy FP-07: Pause & Confirm",
        "clause": "High-risk payments are paused individually and confirmed with the customer via chat or OTP. The customer's account is never frozen for a single suspicious payment.",
        "keywords": ["pause", "otp", "confirm", "payment", "hold", "scam", "freeze"],
    },
    {
        "doc_id": "CLM-POL-12",
        "category": "CLAIMS_POLICY",
        "title": "Claims Policy CLM-12: Payment-Proof Reconciliation",
        "clause": "A claimed amount must be supported by a ledger-verified payment to the repair vendor. If the claim exceeds the verified payment by more than 10%, or the invoice is a duplicate, route to an adjuster; any payout is capped at the verified amount less the deductible.",
        "keywords": ["claim", "insurance", "invoice", "payout", "adjuster", "duplicate", "deductible", "inflated"],
    },
]

PRODUCTS: list[dict[str, Any]] = [
    {
        "product_id": "PROD-INV-FIN-01",
        "title": "Smart Invoice Credit Line",
        "apr_pct": 6.45,
        "limit_usd": 45000.00,
        "kind": "credit",
        "terms": "Pre-qualified revolving credit for verified inflows over $10,000/month, built for 14-to-30-day cash-flow gaps. No overdraft fees; repay when the invoice lands.",
        "min_monthly_inflow_usd": 10000.00,
    },
    {
        "product_id": "PROD-SAV-SWEEP-02",
        "title": "Auto-Sweep Savings Vault",
        "apr_pct": 7.10,
        "limit_usd": 0.0,
        "kind": "savings",
        "terms": "Sweeps surplus balance above your safety buffer into a 7.10% savings vault and sweeps it back automatically before a dip.",
        "min_monthly_inflow_usd": 0.0,
    },
]

AML_CASE: dict[str, Any] = {
    "case_id": "AM-89412",
    "subject_customer_id": "AML-303",
    "window_hours": 72,
    "nodes": [
        {"id": "A", "name": "Shell Co. A", "country": "AE"},
        {"id": "B", "name": "Transit Account B", "country": "SG"},
        {"id": "C", "name": "Global Traders C", "country": "HK"},
        {"id": "D", "name": "Holding Co. D", "country": "IN"},
    ],
    # BigQuery transfer rows within the 72h window
    "transfers": [
        {"tx_id": "TX-A1", "from": "A", "to": "B", "amount_usd": 300000.00, "ts": "2026-10-11T09:12:00"},
        {"tx_id": "TX-B1", "from": "B", "to": "C", "amount_usd": 300000.00, "ts": "2026-10-11T21:40:00"},
        {"tx_id": "TX-C1", "from": "C", "to": "D", "amount_usd": 300000.00, "ts": "2026-10-12T14:05:00"},
        {"tx_id": "TX-D1", "from": "D", "to": "A", "amount_usd": 300000.00, "ts": "2026-10-13T08:30:00"},
    ],
    "supporting_invoices": 0,
}

BASE_KPIS: dict[str, Any] = {
    "transactions_monitored": 12480,
    "fraud_blocked_count": 37,
    "fraud_blocked_usd": 412300.00,
    "loans_pending": 14,
    "open_aml_cases": 3,
    "open_alerts": 9,
    "projected_savings_usd": 1840000.00,
    # Customer friction (problem statement pain point 1: blocking the wrong people)
    "interception_rate_pct": 99.4,
    "false_hold_hours": 11.2,
    "false_hold_hours_delta_pct": -42.0,
    "false_positive_rate_pct": 0.18,
    "holds_confirmed_by_customer": 0,
    # Operations
    "compliance_score_pct": 98.7,
    "doc_stp_rate_pct": 94.2,
    "on_time_disbursal_pct": 99.1,
    "risk_margin_bps": 142,
    "growth_offers_sent": 0,
    "growth_nii_usd": 0.0,
    "claims_pending": 6,
}

# Labelled AI interventions already on the impact chart (index into SAVINGS_SERIES)
HISTORIC_INTERVENTIONS: list[dict[str, Any]] = [
    {"index": 5, "label": "Pub/Sub + Vertex AI mule block", "savings_usd": 310000.00},
    {"index": 8, "label": "Document AI income catch", "savings_usd": 420000.00},
    {"index": 10, "label": "Gemini scam shield", "savings_usd": 285000.00},
]

# Growth action from the cash-flow forecast (not a risk alert)
GROWTH_CAMPAIGN: dict[str, Any] = {
    "segment_size": 340,
    "expected_nii_usd": 410000.00,
    "product_id": "PROD-INV-FIN-01",
}

# Insurance claims (R3.5). Ledger = verified payments in BigQuery.
CLAIMS: dict[str, dict[str, Any]] = {
    "claim_clean": {
        "claim_id": "CL-5530",
        "filename": "Claim_Aarav_Laptop_Damage.pdf",
        "processor_type": "INVOICE_PROCESSOR + CLAIM_FORM",
        "customer_id": "CUST-101",
        "policy": {"policy_id": "POL-GAD-2231", "cover": "Gadget accidental damage", "limit_usd": 3000.00, "deductible_usd": 100.00},
        "fields": {
            "claimant": "Aarav Sharma",
            "incident": "Laptop screen and keyboard damage",
            "repair_vendor": "QuickFix Electronics",
            "invoice_number": "QF-11872",
            "claimed_amount_usd": 1850.00,
            "invoice_date": "2026-10-02",
            "ocr_confidence": 0.996,
        },
        "ledger_payment": {"payee": "QuickFix Electronics", "amount_usd": 1850.00, "date": "2026-10-02", "tx_id": "TX-7720"},
        "tamper_signals": [],
        "lines": [
            {"date": "2026-10-02", "desc": "Screen replacement", "amount_usd": 1240.00},
            {"date": "2026-10-02", "desc": "Keyboard assembly", "amount_usd": 460.00},
            {"date": "2026-10-02", "desc": "Labour", "amount_usd": 150.00},
            {"date": "2026-10-02", "desc": "Invoice total", "amount_usd": 1850.00, "summary": True},
        ],
    },
    "claim_inflated": {
        "claim_id": "CL-7741",
        "filename": "Claim_ApexMfg_Machinery_Breakdown.pdf",
        "processor_type": "INVOICE_PROCESSOR + CLAIM_FORM",
        "customer_id": "SME-202",
        "policy": {"policy_id": "POL-MBD-8890", "cover": "Machinery breakdown", "limit_usd": 200000.00, "deductible_usd": 5000.00},
        "fields": {
            "claimant": "Apex Manufacturing Pvt Ltd",
            "incident": "CNC spindle motor failure",
            "repair_vendor": "Precision Tools Ltd",
            "invoice_number": "PT-2026-0412",
            "claimed_amount_usd": 175000.00,
            "invoice_date": "2026-09-21",
            "ocr_confidence": 0.989,
        },
        "ledger_payment": {"payee": "Precision Tools Ltd", "amount_usd": 112500.00, "date": "2026-09-23", "tx_id": "TX-6604"},
        "tamper_signals": [
            "Invoice total edited: line items sum to $112,500",
            "Same invoice number PT-2026-0412 seen on a 2025 claim (duplicate)",
        ],
        "lines": [
            {"date": "2026-09-21", "desc": "Spindle motor (OEM)", "amount_usd": 84000.00},
            {"date": "2026-09-21", "desc": "Installation & calibration", "amount_usd": 21000.00},
            {"date": "2026-09-21", "desc": "Freight", "amount_usd": 7500.00},
            {"date": "2026-09-21", "desc": "Invoice total", "amount_usd": 175000.00, "summary": True, "tampered": True},
        ],
    },
}

# Business lines for the division overview. Volumes are sample portfolio data.
DIVISIONS: list[dict[str, Any]] = [
    {"id": "retail", "icon": "💳", "name": "Retail & Instant Payments", "hub": "Mumbai & Bengaluru · Pub/Sub stream",
     "metrics": [["STP rate", "99.4%"], ["Daily volume", "$142.8M"], ["Active users", "1.24M"], ["Analysts online", "42"]]},
    {"id": "sme", "icon": "🏢", "name": "SME & Commercial Lending", "hub": "Delhi NCR & Pune · Document AI",
     "metrics": [["Underwriting STP", "91.8%"], ["Loan pipeline", "$68.4M"], ["Active files", "3,410"], ["Underwriters", "28"]]},
    {"id": "insurance", "icon": "🛡️", "name": "Digital Insurance & Claims", "hub": "Chennai & Hyderabad · Claims AI",
     "metrics": [["Auto-adjudication", "94.6%"], ["Claims value", "$29.1M"], ["Active policies", "480K"], ["Avg payout", "4.2 min"]]},
    {"id": "treasury", "icon": "🌐", "name": "Cross-Border Treasury & AML", "hub": "GIFT City · BigQuery graph",
     "metrics": [["Compliance SLA", "88.5%"], ["FX flow", "$215.0M"], ["Entities monitored", "18,900"], ["Investigators", "15"]]},
]

# Sample portfolio analytics (illustrative, not computed)
ANALYTICS: dict[str, Any] = {
    "doc_readiness": {"center": "94%", "caption": "STP health", "segments": [
        ["Verified auto-approve", 73, "#16a34a"], ["Income discrepancy", 15, "#d97706"],
        ["Scheduled review", 7, "#2563eb"], ["Tampered / forged", 5, "#dc2626"]],
        "facts": [["Open loan files", "142"], ["Manual backlog", "9 (1.4h)"], ["Doc AI templates", "100% ready"], ["Fraud prevented", "$890K"]]},
    "investigators": {"center": "104", "caption": "Officers", "segments": [
        ["Available capacity", 40, "#16a34a"], ["Active case review", 38, "#2563eb"],
        ["AI policy calibration", 15, "#7c3aed"], ["Overloaded / SLA risk", 7, "#dc2626"]],
        "insight": "Auto-drafting SARs with Vertex AI Search cut AML investigation time from 4.2 hours to 18 minutes."},
    "threats": [
        {"title": "Phishing invoice lures", "value": "128 blocked", "badge": "+34% spike", "tone": "bad", "series": [4, 8, 6, 14, 18, 25], "note": "Fake GST/routing PDFs caught by Gemini"},
        {"title": "Synthetic KYC velocity", "value": "19 flagged", "badge": "Watch", "tone": "warn", "series": [10, 9, 13, 11, 19, 17], "note": "Document AI font/metadata anomaly check"},
        {"title": "Bureau & account aggregator", "value": "42 ms avg", "badge": "99.9% reliable", "tone": "ok", "series": [14, 16, 13, 15, 14, 16], "note": "CIBIL / AA pulls with stable latency"},
        {"title": "RBI / FATF policy sync", "value": "1,420 clauses", "badge": "Synced", "tone": "ai", "series": [8, 10, 14, 18, 20, 22], "note": "Indexed in Vertex AI Search"},
    ],
}

# Bank-wide view (not a customer)
GLOBAL_VIEW: dict[str, Any] = {
    "customer_id": "ALL",
    "name": "All Banking Units",
    "short": "All Banking Units (Global View)",
    "segment": "Bank-wide",
    "risk_tier": "Portfolio",
    "kyc_status": "n/a",
    "default_document": None,
    "scenario": {
        "banner": "Global view across retail, SME lending, insurance and treasury",
        "story": "Switch to a customer persona to walk through that customer's journey.",
        "payment": {"recipient": "Offshore Transit Ltd", "amount_usd": 48500.00, "new_device": True},
        "focus_recs": ["REC-AML", "REC-LOAN", "REC-SCAM", "REC-GROWTH"],
        "document_hint": "Pick any statement or claim to verify.",
        "aml_note": "Bank-wide view of open case #AM-89412.",
        "acts_as": "CUST-101",
    },
}

# Monthly risk exposure vs AI savings (USD thousands) for the area chart
SAVINGS_SERIES: list[dict[str, Any]] = [
    {"label": m, "exposure_k": e, "savings_k": s}
    for m, e, s in [
        ("Nov", 820, 310), ("Dec", 870, 360), ("Jan", 910, 420), ("Feb", 880, 470),
        ("Mar", 950, 530), ("Apr", 990, 610), ("May", 1020, 700), ("Jun", 1060, 790),
        ("Jul", 1110, 880), ("Aug", 1150, 990), ("Sep", 1190, 1120), ("Oct", 1240, 1250),
    ]
]
