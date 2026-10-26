# Architecture

![Architecture diagram](architecture-diagram.png)

(Source of the diagram: [`architecture-diagram.mmd`](architecture-diagram.mmd), rendered with Mermaid CLI.)

## 1. Components and their boundaries

| Layer | Code | Responsibility |
|---|---|---|
| User interface | `apps/frontend/` | Chat, alarm summary, causes/recommendations, citations, MCP trace, tool discovery, export. Escapes all text before display. |
| Copilot API | `apps/backend/app.py` | HTTP endpoints (`/`, `/api/chat`, `/api/tools`, `/api/documents`, `/health`), input validation, request logging. |
| Orchestration | `apps/backend/workflow.py` | LangGraph `StateGraph`: decides which tools to call, passes outputs between tools, calls RAG, builds the result. Conversation memory via `MemorySaver`. |
| Planning | `apps/backend/planner.py` | Intent detection and entity extraction (asset, site, unit, time range, severity, status). |
| Evidence combination | `apps/backend/answer.py` | Likely causes, API-vs-document check, related assets, procedure, markdown/LLM answer. |
| MCP client / tool registry | `apps/backend/mcp_client.py` | Opens the MCP session (stdio or HTTP), discovers tools, validates arguments against JSON schemas, enforces timeouts, records the trace. |
| MCP server | `mcp-servers/alarm-management/` | 9 typed tools, input/output validation, error mapping, structured logs, health route. |
| API connector | `connectors/alarm_api_client.py` | Auth header, trace headers, timeout, retry with back-off, pagination, error mapping. |
| Source system | `apps/alarm_simulator/` | Alarm Management API simulator built from the Postman collections. |
| RAG ingestion | `rag/ingestion/ingest.py` | Load documents, metadata, chunking, injection flagging, JSON index. |
| Retrieval service | `rag/retrieval/retriever.py`, `rag/safety.py` | Filtered hybrid search, confidence status, sanitising, citations. |
| Domain models | `mcp-servers/alarm-management/alarm_schemas.py`, `apps/alarm_simulator/main.py` (request models) | Typed contracts on both sides of the API. |
| Configuration | `.env.example`, environment variables | No secrets in code; each service reads only what it needs. |
| Observability | JSON log lines in all three services | request id, conversation id, trace id, tool, duration, outcome, API status, attempts, retrieval query, chunk ids + scores, answer source. |
| Persistence | `MemorySaver` (in-process), JSON index file | Enough for the assignment; swap for Postgres saver / vector DB in production. |

## 2. Request flow (prompt → grounded answer)

Example: *"Investigate recurring high-severity alarms for Boiler Feed Pump 101 over the last 90 days ..."*

1. **GUI** sends `POST /api/chat {message, thread_id}`.
2. **FastAPI** validates the body (1–2000 chars, safe thread id) and calls `run_copilot()`.
3. `run_copilot()` creates a `trace_id`, opens **one MCP session** (`open_toolbox`) and runs the LangGraph graph with that session.
4. **`plan`** – `make_plan()` detects intent `investigation`, asset `Boiler Feed Pump 101`, severity `high, critical`, time range = last 90 days, and the steps to run.
5. **`discover_tools`** – MCP `tools/list`. The tool names and JSON schemas are stored; every later call is checked against them.
6. **`resolve_scope`** – MCP `search_assets("Boiler Feed Pump 101")` → `AST-BFP-101`. If nothing matches well the graph jumps straight to `compose_answer` and asks the user to clarify.
7. **`fetch_alarms`** – MCP `get_alarms(asset_id=AST-BFP-101, severity, start, end, fetch_all_pages=true)`. The focus alarm is chosen (active first, then severity, then most recent; or the alarm type mentioned in the question).
8. **`analyze_alarms`** – MCP `get_alarm_summary`, `get_alarm_trends`, `correlate_alarms` (correlation includes related assets).
9. **`prioritize_and_recommend`** – MCP `score_alarm_priority(alarm_id from step 7)` and `get_operator_recommendations(alarm_id)` – output of one tool is the input of the next.
10. **`asset_context`** – MCP `get_asset_metadata` → asset type and related assets.
11. **`retrieve_documents`** – RAG query = asset name + focus alarm + intent hint + the user's words; filter = asset type + related asset types + `general`. Weak results → retry without filter + warning. Injected sentences are removed.
12. **`compose_answer`** – builds the structured result:
    - *measured* causes from correlation `[T6]`, *documented* causes from retrieved chunks `[D1]`;
    - each API recommendation compared with document sentences → supported / conflict / not covered;
    - related assets, applicable procedure, warnings (failed steps, low confidence, removed injections, assumptions);
    - answer text by the LLM (if configured) or by the template.
13. The context (`assets`, `alarm_id`) is saved in the checkpointer for follow-up questions; the response goes back to the GUI with the full trace and citations.

Every MCP call also carries the `trace_id`; the MCP server forwards it to the Alarm API as `trace_id`/`x-trace-id`, the API echoes it back, and all three services log it – one id follows the request across all hops.

## 3. MCP path vs RAG path

```text
MCP path:  GUI -> /api/chat -> LangGraph node -> McpToolbox.call() -> [MCP protocol: stdio | HTTP]
           -> FastMCP tool (validation) -> AlarmApiClient (auth, retry, timeout) -> Alarm API simulator

RAG path:  rag/documents/*.md -> ingest.py (metadata, chunks, injection flag) -> rag/index/*.json
           LangGraph retrieve_documents -> DocumentRetriever.search (filters, hybrid score, sanitise) -> citations
```

Both paths join in `compose_answer`; neither is a separate demo.

## 4. Authentication and trust boundaries

| Boundary | Control |
|---|---|
| Browser → copilot | Input validation (length, thread id pattern). Output is HTML-escaped before rendering. (No user login – see limitations.) |
| Copilot → MCP server | Copilot holds **no API token**. stdio: child process; HTTP: internal docker network. Only discovered tools can be called; arguments validated against schemas. |
| MCP server → Alarm API | Bearer token from env var, only in the connector. Never logged, never returned, never in error text (tested). |
| Retrieved documents → LLM | Documents are untrusted data: injection sentences removed, documents wrapped in `<document>` tags, system prompt forbids following instructions inside them; vendor documents marked `external`. |
| Write operations | None exist – all tools are read-only, so no approval step is needed for this use case. |

## 5. Failure handling summary

| Failure | Where handled | User sees |
|---|---|---|
| API 5xx / 429 / timeout | connector retries (2×, back-off) | trace shows attempts > 1, or step error |
| API 4xx | connector maps to `NOT_FOUND`, `AUTH_FAILED`, `INVALID_INPUT` | step error with code |
| Invalid tool arguments | copilot JSON-schema check, server Pydantic check | step `invalid_input` |
| Tool not offered | copilot checks discovered list | step `unavailable` |
| Tool hangs | `asyncio.wait_for` per call | step `timeout` |
| Some steps fail | graph continues with what it has | warnings + partial answer |
| MCP server down | `run_copilot` falls back to documents-only mode | warning "MCP server is unavailable" |
| Weak / no documents | retriever status | warning, no fake citations |
| LLM error | `llm_answer` | template answer + warning |
