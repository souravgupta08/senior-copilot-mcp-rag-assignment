# Demo Video Script (≤ 10 minutes)

Before recording: `docker compose up --build` (or the local option in the README), open http://localhost:8080, keep a terminal with the logs visible.

| Time | Show | Say (key points) |
|---|---|---|
| 0:00–0:45 | README top + architecture diagram | Use case, problem, assumptions. "Copilot never calls the API directly – only through my MCP server. RAG and MCP meet in one workflow." |
| 0:45–1:45 | Code tour: `mcp-servers/alarm-management/alarm_mcp_server.py`, `connectors/alarm_api_client.py` | Typed tools, validation, auth from env, retries/timeouts, error mapping, trace headers. |
| 1:45–2:15 | GUI → **MCP tools** button | Tool discovery (`tools/list`) with input and output schemas. |
| 2:15–4:30 | Click **Acceptance scenario** | Walk through: alarm summary, focus alarm P1, measured cause (FCV-101 → pump pressure) `[T6]`, documented causes `[D1]`, recommendations with *supported/conflict*, related assets, procedure SOP-BFP-001. Expand trace T2 (asset resolution) and T7/T8 (alarm id passed between tools), show raw request/response. Open citation D1. |
| 4:30–5:15 | Ask *"What related assets should be inspected for this alarm?"* | Context retention – no new asset search in the trace. |
| 5:15–6:00 | *"Which alarm has the highest priority in EastRefinery, and why?"* | Several `score_alarm_priority` calls, highest one chosen, explanation. |
| 6:00–7:15 | Failure demo: `bash scripts/demo_failure.sh correlation`, ask the acceptance question again | Step T6 fails after 3 attempts, warning card, answer still produced with remaining evidence. Then `flaky` → show attempts > 1 succeeding. `reset`. |
| 7:15–7:45 | Ask *"What does the uploaded copy note in the pump pressure switch bulletin say for Boiler Feed Pump 101?"* | Prompt-injection text removed, red tag, warning. |
| 7:45–8:15 | Ask *"Investigate Pump XYZ 999"* | Graceful handling of incomplete information. |
| 8:15–9:15 | Terminal: `pytest -q`, `bash scripts/run_postman.sh` | 124 tests incl. MCP + RAG end-to-end; Postman collections pass. Show coverage. |
| 9:15–10:00 | `docs/known-limitations.md` | Limitations and next steps. |

Optional: set `GROQ_API_KEY` to show the LLM-written answer (answer footer says "LLM answer").
