# Decision Log

| Date | Decision | Reason |
|---|---|---|
| 2026-10-14 | Python + FastAPI backend | Heavy AI usage; strong Google AI SDK support |
| 2026-10-14 | Google Cloud as target platform | Project goal |
| 2026-10-14 | Build locally first, mock-first services | Run offline without keys; swap to live GCP via config |
| 2026-10-14 | Scope = 3 personas on one customer lifecycle (R1-R5) | Problem statement: siloed fraud, docs, compliance, guidance |
| 2026-10-14 | High-risk payments pause and confirm via chat, never freeze the account | Reduce wrongly blocked customers |
| 2026-10-14 | SARs are drafts; human sign-off required | Regulatory accountability |
| 2026-10-14 | UI reduced to 5 pages + floating Copilot + persona switcher (see ui-spec.md) | Replaces the 11-tab prototype; clearer demo story |
| 2026-10-14 | Light-mode theme; purple reserved for AI/Gemini output | Visual consistency |
| 2026-10-14 | Fraud weights retuned (see MEMORY.md) so the demo payment scores 95% | Match ui-spec while keeping score computed |
| 2026-10-14 | Charts drawn as hand-rolled SVG, no CDN | Runs offline; fewer dependencies |
| 2026-10-14 | Ported features from the legacy HTML: global view, friction KPIs, rich action cards + growth action, divisions, ranked alerts, exposure table, donuts, sparklines, impact panel, GCP strip, search, bell, insurance claims | Strengthen the Command Center; cover R3.5 |
| 2026-10-14 | Alerts, exposure, division health and impact KPIs are computed from live state; donuts, sparklines and division volumes are labelled sample data | Avoid showing made-up numbers as live |
| 2026-10-14 | Planned: multi-agent system (Orchestrator + 4 tool-calling agents) with a live execution trace; code in `app/agents/` | Show agents acting with tools, not a chat box (docs/agents-plan.md) |
| 2026-10-14 | Add Model Armor + Sensitive Data Protection (safety), Vertex AI RAG Engine (grounding), Vertex AI Agent Engine (agent hosting), Gemini Live API + Cloud Translation (voice, languages) | Responsible AI for banking; real citations; managed agents; demo moment |
| 2026-10-14 | Agent context in AGENTS.md, MEMORY.md, docs/ | Shared context for Cortex Code and other agents |
| 2026-10-14 | Adopt teammate's FraudShield backend brief (Section 5) as the API contract; built Phase A endpoints first in `app/routers/fraudshield.py` | Unblocks the frontend; BigQuery pipeline already live on GCP |
| 2026-10-14 | Analyst decisions stored append-only in `fraudshield.case_decisions` (DML INSERT), latest wins | BigQuery cannot reliably UPDATE freshly streamed rows |
| 2026-10-14 | Live BigQuery query failures return 503 rather than silently falling back to mock data | Never show synthetic numbers as live; mock is used only when the client cannot initialise |
| 2026-10-14 | FraudShield thresholds (0.30 / 0.70) coexist with FinGuard payment thresholds (0.40 / 0.75) for now | Different scorers; to be aligned with the team |
