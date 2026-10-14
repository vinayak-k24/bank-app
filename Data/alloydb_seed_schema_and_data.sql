-- =============================================================================
-- FinGuard 360: Cloud SQL / AlloyDB Operational Database Schema & Seed Data
-- Target Service: Google Cloud SQL for PostgreSQL / AlloyDB for PostgreSQL
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS vector;

DROP TABLE IF EXISTS compliance_cases CASCADE;
DROP TABLE IF EXISTS insurance_claims CASCADE;
DROP TABLE IF EXISTS loan_applications CASCADE;
DROP TABLE IF EXISTS verified_beneficiaries CASCADE;
DROP TABLE IF EXISTS customers_accounts CASCADE;

-- 1. Operational Customers & Bank Accounts Table
CREATE TABLE customers_accounts (
    customer_id VARCHAR(32) PRIMARY KEY,
    full_name VARCHAR(120) NOT NULL,
    entity_type VARCHAR(40) NOT NULL,
    segment VARCHAR(80) NOT NULL,
    account_number VARCHAR(32) UNIQUE NOT NULL,
    ifsc_routing VARCHAR(24) NOT NULL,
    pan_tax_id VARCHAR(24) UNIQUE NOT NULL,
    email VARCHAR(120),
    phone VARCHAR(32),
    city VARCHAR(64),
    current_balance_usd NUMERIC(14, 2) NOT NULL,
    verified_monthly_inflow_usd NUMERIC(14, 2) NOT NULL,
    avg_monthly_outflow_usd NUMERIC(14, 2) NOT NULL,
    dti_ratio_pct NUMERIC(5, 2),
    credit_score INT,
    risk_tier VARCHAR(40) NOT NULL,
    kyc_status VARCHAR(40) NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO customers_accounts (
    customer_id, full_name, entity_type, segment, account_number, ifsc_routing,
    pan_tax_id, email, phone, city, current_balance_usd, verified_monthly_inflow_usd,
    avg_monthly_outflow_usd, dti_ratio_pct, credit_score, risk_tier, kyc_status
) VALUES
('CUST-101', 'Aarav Sharma', 'RETAIL_FREELANCE', 'Retail & Freelance UX Consultant', 'AC-8840192011', 'FING0001024', 'ABCPS4921K', 'aarav.sharma@designstudio.in', '+91-98201-44910', 'Mumbai', 128450.00, 14250.00, 9500.00, 18.40, 782, 'LOW', 'VERIFIED'),
('SME-202', 'Apex Manufacturing Pvt Ltd', 'SME_CORPORATE', 'SME Commercial Lending (Auto Components)', 'AC-5520918442', 'FING0002088', 'AABCA8841M', 'finance@apexmfg-pune.in', '+91-98230-77120', 'Pune', 84300.00, 12400.00, 10333.33, 44.20, 665, 'HIGH_WATCH_DISCREPANCY', 'STEP_UP_REQUIRED'),
('INS-404', 'Priya Nair', 'RETAIL_POLICYHOLDER', 'Retail Banking & Digital Insurance', 'AC-3310498210', 'FING0001024', 'AKLPN7732F', 'priya.nair@techmail.in', '+91-98450-33219', 'Bengaluru', 19200.00, 6800.00, 4900.00, 24.00, 748, 'MEDIUM_CLAIM_AUDIT', 'VERIFIED'),
('AML-301', 'Zenith Imports LLP (Shell Co. A)', 'SHELL_ENTITY', 'Cross-Border Trade & Treasury', 'AC-9900112201', 'FING0009901', 'AAACZ1001A', 'ops@zenithimports.io', '+44-20-7946-0991', 'GIFT City', 1200000.00, 95000.00, 92000.00, 12.00, 610, 'CRITICAL_AML_RING', 'FROZEN_PENDING_SAR'),
('AML-302', 'Nova Logistics Pvt Ltd (Transit B)', 'SHELL_ENTITY', 'Cross-Border Trade & Treasury', 'AC-9900112202', 'FING0009901', 'AAACN1002B', 'accounts@novalogistics.in', '+91-22-4091-8821', 'Mumbai', 310000.00, 40000.00, 39500.00, 15.00, 605, 'CRITICAL_AML_RING', 'FROZEN_PENDING_SAR'),
('AML-303', 'Pacific Exim Corp (Global Traders C)', 'SHELL_ENTITY', 'Cross-Border Trade & Treasury', 'AC-9900112203', 'FING0009901', 'AAACP1003C', 'trade@pacificexim.co', '+91-44-2819-3300', 'Chennai', 285000.00, 52000.00, 51000.00, 14.50, 598, 'CRITICAL_AML_RING', 'FROZEN_PENDING_SAR'),
('AML-304', 'Meridian Ventures Holding (Holding Co. D)', 'SHELL_ENTITY', 'Cross-Border Trade & Treasury', 'AC-9900112204', 'FING0009901', 'AAACM1004D', 'treasury@meridianhold.com', '+91-11-4100-9920', 'Delhi NCR', 405000.00, 30000.00, 29800.00, 19.00, 590, 'CRITICAL_AML_RING', 'FROZEN_PENDING_SAR'),
('CUST-105', 'Rohan Deshmukh', 'RETAIL_SALARIED', 'Retail Prime Banking', 'AC-8840192015', 'FING0001024', 'ADEPD1120R', 'rohan.d@corp.in', '+91-98111-22001', 'Mumbai', 64200.00, 8500.00, 5200.00, 21.00, 790, 'LOW', 'VERIFIED'),
('CUST-106', 'Kavita Krishnan', 'RETAIL_SALARIED', 'Retail Wealth Management', 'AC-8840192016', 'FING0001024', 'AKLPK8831M', 'kavita.k@wealth.in', '+91-98400-11223', 'Chennai', 215000.00, 19400.00, 11200.00, 14.20, 815, 'LOW', 'VERIFIED'),
('SME-207', 'Deccan Precision Tools LLP', 'SME_CORPORATE', 'SME Commercial Lending', 'AC-5520918449', 'FING0002088', 'AABCD4419P', 'billing@deccantools.in', '+91-98220-55110', 'Belagavi', 92400.00, 16800.00, 12100.00, 29.50, 742, 'LOW', 'VERIFIED');

-- 2. Whitelisted / Verified Beneficiaries Table (Used by Scam Guard)
CREATE TABLE verified_beneficiaries (
    beneficiary_id VARCHAR(32) PRIMARY KEY,
    owner_customer_id VARCHAR(32) REFERENCES customers_accounts(customer_id),
    vendor_legal_name VARCHAR(120) NOT NULL,
    verified_email_domain VARCHAR(80) NOT NULL,
    verified_billing_email VARCHAR(120) NOT NULL,
    verified_account_number VARCHAR(32) NOT NULL,
    account_last4 VARCHAR(4) NOT NULL,
    verified_ifsc_routing VARCHAR(24) NOT NULL,
    historical_monthly_payment_usd NUMERIC(14, 2) NOT NULL,
    trust_status VARCHAR(32) NOT NULL
);

INSERT INTO verified_beneficiaries VALUES
('VEND-901', 'CUST-101', 'NetCorp Cloud Services LLC', 'netcorp.com', 'billing@netcorp.com', 'AC-7700222209', '2209', 'FING0004400', 2450.00, 'VERIFIED_WHITELISTED'),
('VEND-902', 'SME-202', 'Jindal Steel Raw Coils Ltd', 'jindalsteel.com', 'ar@jindalsteel.com', 'AC-4400881120', '1120', 'FING0003100', 3800.00, 'VERIFIED_WHITELISTED'),
('VEND-903', 'SME-202', 'Bharat Auto Components Ltd', 'bharatauto.in', 'payables@bharatauto.in', 'AC-3300119940', '9940', 'FING0002088', 4200.00, 'VERIFIED_WHITELISTED');

-- 3. Loan Applications Table (Used by Page 3 Document AI Underwriting Desk)
CREATE TABLE loan_applications (
    application_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) REFERENCES customers_accounts(customer_id),
    requested_amount_usd NUMERIC(14, 2) NOT NULL,
    tenure_months INT NOT NULL,
    declared_monthly_income_usd NUMERIC(14, 2) NOT NULL,
    bq_verified_monthly_income_usd NUMERIC(14, 2) NOT NULL,
    discrepancy_pct NUMERIC(6, 2) NOT NULL,
    supporting_doc_ids TEXT NOT NULL,
    underwriting_status VARCHAR(40) NOT NULL,
    policy_clause_applied VARCHAR(40) NOT NULL,
    ai_audit_memo TEXT NOT NULL
);

INSERT INTO loan_applications VALUES
('LN-4108', 'CUST-101', 45000.00, 36, 14250.00, 14250.00, 0.00, 'DOC-01,DOC-05', 'INSTANT_PRE_APPROVED', 'UW-104.1', '100% Match between DOC-01 Bank Statement ($14,250/mo), DOC-05 Tax Return ($171,000/yr), and BigQuery ledger. Pre-approved for $45,000 at 6.45% APR.'),
('LN-4092', 'SME-202', 250000.00, 36, 18500.00, 12400.00, 49.19, 'DOC-02,DOC-03,DOC-04,DOC-12', 'HOLD_DISCREPANCY_ALERT', 'UW-104.2', 'CRITICAL HOLD: DOC-02 Page 6 claims $18,500/mo deposits (font patch anomaly), whereas Pages 1-5 and BigQuery verify $12,400/mo (+49.2% inflation). DOC-12 field inspection also notes only 2 of 4 CNC machines present on floor.');

-- 4. Insurance Claims Table (Used by Page 3 Claims Verifier)
CREATE TABLE insurance_claims (
    claim_id VARCHAR(32) PRIMARY KEY,
    customer_id VARCHAR(32) REFERENCES customers_accounts(customer_id),
    policy_number VARCHAR(32) NOT NULL,
    claim_type VARCHAR(40) NOT NULL,
    claimed_amount_usd NUMERIC(14, 2) NOT NULL,
    approved_payout_usd NUMERIC(14, 2) NOT NULL,
    duplicate_deduction_usd NUMERIC(14, 2) NOT NULL,
    supporting_doc_id VARCHAR(32) NOT NULL,
    claim_status VARCHAR(40) NOT NULL,
    ai_claim_finding TEXT NOT NULL
);

INSERT INTO insurance_claims VALUES
('CLM-7741', 'INS-404', 'POL-884120', 'MEDICAL_HOSPITALIZATION', 11450.00, 7750.00, 3200.00, 'DOC-09', 'ADJUSTED_DUPLICATE_FLAGGED', 'DOC-09 Page 4 handwritten doctor note confirms 1x Titanium Implant (Batch #TK99), but Page 7 itemized bill charges Batch #TK99 twice ($3,200 x 2 on Lines 14 & 19). Deducted $3,200 duplicate + $500 deductible per CLM-208.4.'),
('CLM-7749', 'INS-404', 'POL-AUTO-4410', 'AUTO_COLLISION_REPAIR', 4850.00, 4350.00, 0.00, 'DOC-08', 'APPROVED_LESS_DEDUCTIBLE', 'DOC-08 handwritten carbon-pad workshop estimate ($4,850.00) parsed at 93.8% confidence; all 4 parts verified against OEM catalog less $500 policy deductible.');

-- 5. Compliance & AML Cases Table (Used by Page 4 SAR Studio)
CREATE TABLE compliance_cases (
    case_id VARCHAR(32) PRIMARY KEY,
    primary_entity_id VARCHAR(32) REFERENCES customers_accounts(customer_id),
    linked_entity_ids TEXT NOT NULL,
    typology VARCHAR(80) NOT NULL,
    total_exposure_usd NUMERIC(14, 2) NOT NULL,
    vertex_ai_risk_score NUMERIC(4, 3) NOT NULL,
    rbi_fatf_citations TEXT NOT NULL,
    case_status VARCHAR(40) NOT NULL,
    gemini_sar_narrative TEXT NOT NULL
);

INSERT INTO compliance_cases VALUES
('AM-89412', 'AML-301', 'AML-301,AML-302,AML-303,AML-304', 'CIRCULAR_SHELL_LAYERING_72H', 1200000.00, 0.964, 'RBI-KYC-24A,FATF-REDFLAG-3.1,FATF-REDFLAG-4.2', 'SAR_READY_FOR_SUBMISSION', 'Between Oct 11 and Oct 14, 2026, $1,200,000 cycled across Zenith Imports (AML-301), Nova Logistics (AML-302), Pacific Exim (AML-303), and Meridian Ventures (AML-304) within 68 hours. Faxed trade invoices (DOC-11) share identical boilerplate templates and lack customs stamps on Page 6.');
