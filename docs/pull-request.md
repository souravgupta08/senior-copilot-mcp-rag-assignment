# Pull Request – Alarm Investigation Copilot (MCP + RAG)

Use this as the description of the first pull request (`feature/alarm-investigation-copilot` → `main`).

## Summary
Adds a complete vertical slice for the **Alarm Investigation and Procedure Guidance Copilot**: Alarm API simulator, Alarm Management MCP server, MCP client integration, document RAG, LangGraph orchestration and GUI.

## Scope
- Simulator implementing all 15 endpoints from the Postman collections (+ chaos endpoint for failure demos)
- MCP server with 9 typed tools, connector with auth/retry/timeout/trace/error mapping
- RAG: 9-document corpus, ingestion, filtered hybrid retrieval, citations, injection guard
- Copilot: planner, LangGraph workflow, evidence combination (measured vs documented), optional Groq LLM
- GUI: chat, alarm summary, causes, recommendations with document check, citations, MCP trace, tool discovery, export

## Architecture changes
New services: `alarm-api` (:8000), `alarm-mcp` (:9000), `copilot` (:8080). See `docs/architecture.md`.

## MCP tools added
`search_assets`, `get_asset_metadata`, `get_alarms`, `get_alarm_details`, `get_alarm_summary`, `get_alarm_trends`, `correlate_alarms`, `score_alarm_priority`, `get_operator_recommendations`.

## RAG workflow added
`python -m rag.ingestion.ingest` → JSON index → `DocumentRetriever.search()` inside the `retrieve_documents` graph node.

## Screenshots
See `docs/screenshots/` (03 acceptance scenario, 04 MCP trace, 05 citations, 08 partial failure, 09 injection removed).

## Test evidence
- `pytest -q` → 124 passed, coverage 93% (`docs/test-evidence/pytest-and-coverage.txt`)
- newman: 4 collections, 74 requests, 0 failures (`docs/test-evidence/newman-*.txt`)
- `ruff check .` and `ruff format --check .` clean

## Design decisions
See `docs/design-decisions.md`.

## Known limitations
See `docs/known-limitations.md`.

## Review checklist
- [x] Copilot calls the Alarm API only through MCP
- [x] MCP and RAG used in the same workflow
- [x] Citations and MCP trace visible in the GUI
- [x] No secrets committed (`.env` ignored, `.env.example` provided)
- [x] Error paths tested (retry, timeout, invalid input, missing tool, partial failure, MCP down)
- [x] Docs: README, architecture, tool catalog, RAG design, API integration
