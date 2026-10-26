# Design Decisions

| # | Decision | Why | Trade-off |
|---|---|---|---|
| 1 | **Use case: Alarm Investigation and Procedure Guidance** | One MCP server, read-only tools, no extra systems (ticketing/DB) – lets the time go into a complete, well-tested vertical slice. | Fewer moving parts to show than the multi-MCP use case. |
| 2 | **Same stack as my earlier TripMate project** (FastAPI + Jinja2 GUI, LangGraph, langchain-mcp-adapters, FastMCP, Groq) | Proven pattern I already understand; GUI needs no build step. | Not a SPA framework; fine for this scope. |
| 3 | **Simulator built from the Postman collections** with deterministic synthetic data and built-in patterns | Repeatable tests and demos; patterns (valve → pump, cooler → compressor, lube oil → motor) make the analysis meaningful. | Data is not real plant data. |
| 4 | **MCP server owns the API token and the connector** | The copilot can't bypass MCP and never sees secrets; auth/retry/timeouts live in one place. | Single shared service token (no per-user identity). |
| 5 | **Typed Pydantic outputs for every tool** | Clients get `outputSchema` + `structuredContent`; no string parsing. | More code in `alarm_schemas.py`. |
| 6 | **Retries in the connector, timeouts in two layers** | Connector retries only temporary errors (429/5xx/timeout); copilot has an overall per-tool timeout so one stuck tool can't freeze the answer. | Worst-case latency = timeout × attempts. |
| 7 | **Copilot validates arguments against the discovered JSON schema** | Catches bad inputs before a network call and proves the client is schema-aware. | Duplicate of server validation (by design). |
| 8 | **One MCP session per user request** | One stdio process / HTTP session per question, shared by all ~9 calls → ~1 s end-to-end. | Session lifetime tied to the request. |
| 9 | **Rule-based planner instead of LLM tool-calling** | Deterministic, testable, free, no hallucinated tool calls; the graph still selects steps per intent and passes outputs between tools – not a fixed script per sample question. | Less flexible wording; new intents need code. See limitations. |
| 10 | **LangGraph with a conditional edge** | Clear, inspectable steps; easy to add nodes; `MemorySaver` gives conversation context per thread. | In-memory only. |
| 11 | **TF-IDF + keyword hybrid instead of neural embeddings** | Small technical corpus, exact terms matter, no API key/GPU, deterministic tests. | Weaker on synonyms/paraphrases. |
| 12 | **Section-based chunks** | Procedures are organised by section; a section is a good citation unit. | Uneven chunk sizes. |
| 13 | **JSON index, not pickle** | Nothing executable is loaded from disk. | Matrix rebuilt at start-up (ms for this corpus). |
| 14 | **Measured vs documented vs generated kept separate** | The brief asks to distinguish evidence types; operators must know what is data and what is guidance. | Answer is more structured than "chatty". |
| 15 | **Document beats API when they conflict** | Approved procedures are the safety authority; a rule engine suggestion that contradicts the SOP is flagged. | Heuristic conflict detection (negation + shared action verb). |
| 16 | **LLM optional with template fallback** | Runs and tests without paid keys; LLM failure never breaks the answer. | Template text is less fluent. |
| 17 | **Degraded mode when MCP is down** | Operators still get procedure guidance. | Answer clearly says alarm data is missing. |
| 18 | **Escape everything in the GUI; tiny built-in markdown renderer** | No HTML/script injection from LLM or documents; no CDN dependency (works offline/in restricted networks). | Only basic markdown formatting. |
