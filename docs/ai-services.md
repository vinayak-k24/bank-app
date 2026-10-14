# AI Services

## Usage map
| Feature | Service | Notes |
|---|---|---|
| Fraud explanation | Gemini Flash | Explain deterministic score; never change decision |
| Document extraction | Document AI (mock locally) | Bank statements, invoices, KYC IDs |
| Underwriting memo | Gemini | Cite UW-104 |
| SAR drafting | Gemini + Vertex AI Search | Cite RBI/FATF doc_ids |
| Financial Twin advice | Gemini | Ground in product catalog |
| Copilot chat | Gemini | Tools over the services above |

## Guidelines
- Use structured (JSON schema) output for anything the app parses.
- Pass only the minimum needed data; mask PII.
- Always provide a mock response path with the same shape.
- Models: TBD (e.g., gemini-2.5-flash for speed, gemini-2.5-pro for SAR drafting).
