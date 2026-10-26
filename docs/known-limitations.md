# Known Limitations and Future Improvements

## Known limitations

1. **Rule-based planner** - intents and entities come from keywords/regex. Unusual phrasing may fall back to the generic "investigation" intent.
2. **Lexical retrieval** - TF-IDF + keyword overlap; synonyms ("overpressure" vs "high discharge pressure") are not matched as well as with embeddings.
3. **Heuristic conflict check** - an API action "conflicts" when a document sentence with a negation ("do not", "never") shares a risky verb (restart, reset, bypass ...). It can miss subtle conflicts or flag edge cases.
4. **Synthetic data and documents** - deterministic simulator data and documents written for this assignment.
5. **Single shared API token** - no per-user authentication or role-based tool authorisation; the GUI has no login.
6. **In-memory state** - conversation memory (`MemorySaver`) and simulator chaos settings are lost on restart and not shared between replicas.
7. **Template answer without an LLM key** - the default answer is structured but not as fluent as an LLM answer.
8. **English only.**
9. **Correlation is co-occurrence**, not causal analysis; it can show a strong pair that is not a true cause.
10. **Docker not tuned for production** - single image for all services, no resource limits or secrets manager.

## Future improvements

- LLM-based planner using the discovered tool schemas (function calling), with the rule-based planner as a fallback and guard-rails on allowed tools.
- Neural embeddings (e.g. `bge-small`) + a vector DB (pgvector/Qdrant) with hybrid BM25 + vector search and a cross-encoder re-ranker.
- Per-user OAuth between GUI -> copilot -> MCP server, tool-level authorisation by role.
- Postgres checkpointer for persistent conversations; Redis for caching tool results.
- OpenTelemetry tracing (spans per MCP call) instead of correlated JSON logs.
- More MCP tools (flood analysis, rationalization, KPI calculation) and a second MCP server for work orders/tickets with an approval step for writes.
- Streaming the answer and the trace to the GUI as steps complete.
- PDF/DOCX ingestion and scheduled index refresh on document change.
