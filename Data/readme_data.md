# FinGuard 360 — `/data` Directory Guide & Google Cloud Upload Commands

This `/data` directory contains the structured datasets, relational database seeds, live event streams, Document AI ground-truth extractions, and RAG policy chunks that power **FinGuard 360** both locally and on **Google Cloud**.

## 1. Files Inside `/data` & How Each File Is Used

| File Name | Format & Volume | Target Google Cloud Service | What It Contains | How the Backend & UI Use It |
| :--- | :--- | :--- | :--- | :--- |
| **`alloydb_seed_schema_and_data.sql`** | PostgreSQL SQL (`5 Tables`) | **Cloud SQL / AlloyDB** | Creates and seeds `customers_accounts` (10 profiles), `verified_beneficiaries` (whitelisted vendors like NetCorp `2209`), `loan_applications`, `insurance_claims`, and `compliance_cases` | Powers live account balances on **Page 1 & Page 5**, checks whether an invoice's bank account matches a saved vendor on **Page 2**, and stores active loan/claim/SAR statuses on **Pages 3 & 4** |
| **`finguard_bigquery_transactions.csv`** | CSV (`1,500 Rows`, 14 Columns) | **BigQuery** & **Vertex AI (Predictive ML)** | 90 days of historical transactions across all customers (`$14,250/mo` inflows for `CUST-101`, `$12,400/mo` inflows for `SME-202`, and `$1.2M` circular transfers for `AML-301..304`) plus ML features (`velocity_24h_ratio`, `device_trust_score`, `geo_mismatch`, `is_fraud_label`) | Used by **BigQuery** to calculate 30-day rolling deposit averages (proving the `+49.2%` income inflation on Apex Mfg's tampered PDF on **Page 3**) and by **BigQuery ML / Vertex AI** to train the real-time fraud classifier |
| **`bigquery_aml_network_edges.csv`** | CSV (`6 Directed Graph Edges`) | **BigQuery Graph Analytics** | Directed money-transfer hops (`EDGE-01` to `EDGE-04`) showing `$1,200,000` cycling through 4 shell accounts in 68 hours (`Case #AM-89412`), plus normal B2B baseline edges | Renders the interactive 4-account circular money-laundering network map on **Page 4 (Compliance & AML Studio)** |
| **`bigquery_cashflow_30d_forecasts.csv`** | CSV (`60 Daily Rows`) | **BigQuery** & **Vertex AI Forecasting** | 30-day day-by-day projected balances, expected inflows/outflows, stress-test balances, and liquidity dip flags for `CUST-101` (Aarav Sharma) and `SME-202` (Apex Mfg) | Drives the 30-day cash-flow forecast line chart, the `-$4,200` 12-day liquidity dip warning, and the "What-If" expense slider on **Page 5 (Personal Financial Coach)** |
| **`pubsub_live_transaction_stream.json`** | JSON Array (`25 Events`) | **Cloud Pub/Sub** (`transactions-topic`) | 25 timestamped payment payloads starting with 5 scripted high-risk fraud/scam attacks (`0.89–0.97` risk scores) followed by 20 normal daily payments | Published to **Pub/Sub** when you click **"Send Live Payment"** or **"Inject Fraud Event"** on **Page 2**, streaming live rows into the UI transaction feed |
| **`document_ai_all_12_extractions.json`** | JSON Object (`12 Documents`: `DOC-01` to `DOC-12`) | **Document AI** & **Gemini on Vertex AI** | Structured OCR field extractions, confidence scores (`91.2%–99.8%`), line items, and tamper/discrepancy flags for all 12 clean, Xeroxed, and handwritten documents | Populates the split-screen extracted JSON viewer, confidence badges, and mismatch alerts on **Page 3 (Loan & Document Desk)** and **Page 2 (Scam Scanner)** |
| **`finguard_360_structured_mock_data.json`** | Master JSON Bundle | **Vertex AI Search (RAG)** & Local Fallback | Contains `vertex_ai_search_rag_chunks` (`RBI-KYC-24A`, `RBI-KYC-16C`, `FATF-REDFLAG-3.1`, `UW-POLICY-104`, `PROD-CATALOG-2026`) plus a unified copy of all personas and events | Grounds **Gemini 2.5 Pro** in exact RBI/FATF clauses when auto-drafting SARs on **Page 4** and matches eligible banking products on **Page 5** |

## 2. Recommended Folder Structure in Your Codebase

Place the files inside `./data/` at the root of your repository:

```text
your-repo/
├── data/
│   ├── README.md                              # This guide
│   ├── alloydb_seed_schema_and_data.sql       # Cloud SQL / AlloyDB seed
│   ├── finguard_bigquery_transactions.csv     # BigQuery 1,500-row ledger & ML training data
│   ├── bigquery_aml_network_edges.csv         # BigQuery AML circular ring edges
│   ├── bigquery_cashflow_30d_forecasts.csv    # BigQuery 30-day cash-flow projections
│   ├── pubsub_live_transaction_stream.json    # Pub/Sub live payment event stream
│   ├── document_ai_all_12_extractions.json    # Document AI outputs for DOC-01..DOC-12
│   ├── finguard_360_structured_mock_data.json # RAG chunks & master fallback bundle
│   └── generated-docs/                                  # Place generated PDFs/images (DOC-01..DOC-12) here
├── app/
```

## 3. Step-by-Step Commands to Push `/data` to Google Cloud

### Step 0: Set Your Google Cloud Environment Variables
Run these in your terminal before executing the upload commands:

```bash
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export BQ_DATASET="finguard_analytics"
export GCS_BUCKET="finguard-360-data-${PROJECT_ID}"
export DB_INSTANCE="finguard-pg-instance"
export DB_NAME="finguard"

gcloud config set project ${PROJECT_ID}
```

### Step 1: Create Cloud Storage Bucket & Upload JSON / Document Files
Upload the structured JSON files and any generated PDFs in `./data/docs/` to Google Cloud Storage:

```bash
# 1. Create the Cloud Storage bucket
gcloud storage buckets create gs://${GCS_BUCKET} --location=${REGION}

# 2. Upload all structured data files and RAG JSON chunks
gcloud storage cp ./data/*.json ./data/*.csv ./data/*.sql gs://${GCS_BUCKET}/structured/

# 3. Upload sample PDFs / images (once placed in ./data/docs/) for Document AI
gcloud storage cp ./data/docs/* gs://${GCS_BUCKET}/documents/
```

### Step 2: Push CSV Files to BigQuery & Train the Vertex AI Fraud Model
Create the BigQuery dataset, load all three CSV files, and train the fraud anomaly model in BigQuery ML (registered directly to **Vertex AI**):

```bash
# 1. Create the BigQuery dataset
bq --location=${REGION} mk -d --description "FinGuard 360 Risk & Transaction Analytics" ${PROJECT_ID}:${BQ_DATASET}

# 2. Load the 1,500-row historical transactions CSV
bq load --autodetect --source_format=CSV --replace \
  ${BQ_DATASET}.transactions_history \
  ./data/finguard_bigquery_transactions.csv

# 3. Load the AML circular network edges CSV
bq load --autodetect --source_format=CSV --replace \
  ${BQ_DATASET}.aml_network_edges \
  ./data/bigquery_aml_network_edges.csv

# 4. Load the 30-day cash-flow forecast series CSV
bq load --autodetect --source_format=CSV --replace \
  ${BQ_DATASET}.cashflow_30d_forecasts \
  ./data/bigquery_cashflow_30d_forecasts.csv

# 5. Train the Fraud Anomaly Classifier in BigQuery ML and register it to Vertex AI
bq query --use_legacy_sql=false "
CREATE OR REPLACE MODEL \`${PROJECT_ID}.${BQ_DATASET}.vertex_fraud_classifier\`
OPTIONS(
  model_type='BOOSTED_TREE_CLASSIFIER',
  input_label_cols=['is_fraud_label'],
  model_registry='vertex_ai',
  vertex_ai_model_id='finguard_fraud_anomaly_detector'
) AS
SELECT
  amount_usd,
  device_trust_score,
  CAST(geo_mismatch AS INT64) AS geo_mismatch_flag,
  velocity_24h_ratio,
  tx_type,
  merchant_category,
  is_fraud_label
FROM \`${PROJECT_ID}.${BQ_DATASET}.transactions_history\`;
"
```

### Step 3: Seed Cloud SQL / AlloyDB with Operational Banking Tables
Import `alloydb_seed_schema_and_data.sql` into your Cloud SQL or AlloyDB PostgreSQL instance:

```bash
# Option A: Import directly from your Cloud Storage bucket into Cloud SQL
gcloud sql import sql ${DB_INSTANCE} \
  gs://${GCS_BUCKET}/structured/alloydb_seed_schema_and_data.sql \
  --database=${DB_NAME}

# Option B: Or run directly via psql if connected via Cloud SQL Auth Proxy / local Postgres
psql -h 127.0.0.1 -U postgres -d ${DB_NAME} -f ./data/alloydb_seed_schema_and_data.sql
```

### Step 4: Create Cloud Pub/Sub Topic & Test Live Transaction Streaming
Create the Pub/Sub topic and subscription, then publish a test fraud event from `pubsub_live_transaction_stream.json`:

```bash
# 1. Create the transactions topic and backend worker subscription
gcloud pubsub topics create transactions-topic
gcloud pubsub subscriptions create transactions-worker-sub --topic=transactions-topic

# 2. Publish the first high-risk transaction event from pubsub_live_transaction_stream.json
gcloud pubsub topics publish transactions-topic \
  --message="$(jq -c '.[0]' ./data/pubsub_live_transaction_stream.json)"
```

### Step 5: Index Policy & Product Knowledge Base in Vertex AI Search
Prepare and import the RAG knowledge chunks (`RBI-KYC-24A`, `FATF-REDFLAG-3.1`, `UW-POLICY-104`, `PROD-CATALOG-2026`) into **Vertex AI Search**:

```bash
# Convert vertex_ai_search_rag_chunks into newline-delimited JSON (JSONL) and upload to GCS
jq -c '.vertex_ai_search_rag_chunks[] | {id: .chunk_id, structData: ., content: {mimeType: "text/plain", rawBytes: (.text | @base64)}}' \
  ./data/finguard_360_structured_mock_data.json > ./data/vertex_ai_search_import.jsonl

gcloud storage cp ./data/vertex_ai_search_import.jsonl gs://${GCS_BUCKET}/rag_kb/
```
Then in **Google Cloud Console → Agent Builder → Data Stores**, select **Cloud Storage**, point to `gs://${GCS_BUCKET}/rag_kb/vertex_ai_search_import.jsonl`, and click **Import**.

## 4. How the Backend Uses `/data` in Local vs. Cloud Mode

* **Instant Local / Demo Mode (`USE_LOCAL_MOCK_DATA=true`):** Your FastAPI backend reads `./data/*.json` and `./data/*.csv` directly from disk so every UI page, chart, Document AI check, and Pub/Sub simulation works with zero latency even before cloud credentials are attached.
* **Live Google Cloud Mode (`USE_LOCAL_MOCK_DATA=false`):** The exact same endpoints query your live **AlloyDB/Cloud SQL** tables, run SQL against **BigQuery**, publish events to **Pub/Sub**, score anomalies via your **Vertex AI** endpoint, and pass **Vertex AI Search** citations to **Gemini 2.5 Pro**.
