"""
Generates docs/mcp-tool-catalog.md from the REAL MCP server:
tool names, descriptions, input/output schemas and a live example call for each tool.

Needs the simulator running (make simulator) and ALARM_API_TOKEN set.
Usage: python scripts/generate_tool_catalog.py
"""

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from apps.backend.mcp_client import open_toolbox, shorten  # noqa: E402

RANGE = {"start_time": "2026-07-28T00:00:00Z", "end_time": "2026-10-26T00:00:00Z"}

EXTRA = {
    "search_assets": ("GET /assets/search", "Resolve a name like 'Boiler Feed Pump 101' to an asset id."),
    "get_asset_metadata": ("GET /assets/{asset_id}/metadata", "Asset context and related assets."),
    "get_alarms": (
        "GET /alarms (follows pagination when fetch_all_pages=true, max 5 pages)",
        "Active or historical alarms for an asset, site or unit.",
    ),
    "get_alarm_details": ("GET /alarms/{alarm_id}", "One alarm by id."),
    "get_alarm_summary": ("POST /alarms/summary", "Counts, recurring rate, ack delay grouped by alarm name."),
    "get_alarm_trends": ("POST /alarms/trends", "Alarm rate per day/week and trend direction."),
    "correlate_alarms": ("POST /alarms/correlation", "Alarms that happen together -> likely causes."),
    "score_alarm_priority": ("POST /alarms/priority-score", "0-100 priority with explanation."),
    "get_operator_recommendations": (
        "POST /recommendations/operator-actions",
        "API recommended actions + related assets.",
    ),
}


async def main():
    async with open_toolbox("catalog") as toolbox:
        tools = await toolbox.discover()
        examples = {}
        search = await toolbox.call("search_assets", {"query": "Boiler Feed Pump 101", "limit": 2})
        asset_id = search["results"][0]["asset_id"]
        alarms = await toolbox.call("get_alarms", {"asset_id": asset_id, "status": "active", "page_size": 2})
        alarm_id = alarms["alarms"][0]["alarm_id"]
        calls = {
            "search_assets": {"query": "Boiler Feed Pump 101", "limit": 2},
            "get_asset_metadata": {"asset_id": asset_id},
            "get_alarms": {"asset_id": asset_id, "status": "active", "page_size": 2},
            "get_alarm_details": {"alarm_id": alarm_id},
            "get_alarm_summary": {"asset_ids": [asset_id], **RANGE, "severity": ["high", "critical"]},
            "get_alarm_trends": {"asset_ids": [asset_id], **RANGE, "bucket": "weekly"},
            "correlate_alarms": {"asset_ids": [asset_id], **RANGE, "min_support": 5},
            "score_alarm_priority": {"alarm_id": alarm_id},
            "get_operator_recommendations": {"alarm_id": alarm_id},
        }
        for name, args in calls.items():
            examples[name] = (args, await toolbox.call(name, args))
        error_example = await toolbox.call("get_asset_metadata", {"asset_id": "AST-XXX-999"})
        error_step = toolbox.trace[-1]
        assert error_example is None

    lines = [
        "# MCP Tool Catalog - Alarm Management MCP Server",
        "",
        "_Generated from the running server by `python scripts/generate_tool_catalog.py`._",
        "",
        "Server: `mcp-servers/alarm-management/alarm_mcp_server.py` (FastMCP). Transports: stdio (default) "
        "or streamable HTTP on `http://<host>:9000/mcp`.",
        "",
        "## Behaviour shared by every tool",
        "",
        "| Topic | Behaviour |",
        "|---|---|",
        "| Authentication | The server reads `ALARM_API_TOKEN` from its environment and sends "
        "`Authorization: Bearer <token>` to the Alarm API. The token is never returned, logged or put in errors. "
        "MCP clients do not need (and never see) the API token. |",
        "| Input validation | Pydantic types on every argument (id patterns like `^AST-[A-Z]{3}-\\d{3}$`, "
        "ISO timestamps, enums, min/max). The copilot also validates against the published JSON schema before "
        "calling. Business checks (start < end, at least one scope filter) raise `[INVALID_INPUT]`. |",
        "| Output validation | Every tool returns a Pydantic model -> published `outputSchema` "
        "+ `structuredContent`. |",
        "| Trace metadata | Optional `trace_id` argument. Forwarded to the API as `trace_id` / `x-trace-id` "
        "headers together with `x-client-id: alarm-mcp-server`. Returned in `meta.trace_id`. |",
        "| Timeout | `ALARM_API_TIMEOUT_SECONDS` (default 10 s) per HTTP attempt. The copilot adds an overall "
        "`MCP_TOOL_TIMEOUT_SECONDS` (default 30 s) per tool call. |",
        "| Retry | Up to `ALARM_API_MAX_RETRIES` (default 2) retries with exponential back-off (0.3 s, 0.6 s) on "
        "timeouts, connection errors, 429 and any 5xx (a `Retry-After` header is honoured, max 5 s). "
        "Other 4xx errors are not retried. `meta.attempts` shows how "
        "many tries were needed. |",
        "| Errors | API errors become MCP tool errors (`isError=true`) with text "
        "`[CODE] message (status=..., attempts=..., trace_id=...)`. Codes: `INVALID_INPUT` (400/422), "
        "`AUTH_FAILED` (401/403), `NOT_FOUND` (404), `RATE_LIMITED` (429), `UPSTREAM_ERROR` (5xx), "
        "`TIMEOUT`, `CONNECTION_FAILED`. |",
        "| Logging | One JSON line per call on stderr: tool, outcome, api_status, attempts, retries, trace_id, "
        "duration_ms. |",
        "",
        f"Example error (`get_asset_metadata` with an unknown id):\n\n```text\n{error_step['error']}\n```",
        "",
        "## Tools",
        "",
    ]

    for tool in tools:
        name = tool["name"]
        operation, purpose = EXTRA.get(name, ("-", "-"))
        args, response = examples[name]
        lines += [
            f"### `{name}`",
            "",
            f"**Purpose:** {purpose}  ",
            f"**Description shown to clients:** {tool['description'].strip()}  ",
            f"**Underlying API operation:** `{operation}`  ",
            "**Auth / errors / timeout:** see shared behaviour above.",
            "",
            "<details><summary>Input schema</summary>\n",
            "```json",
            json.dumps(tool["input_schema"], indent=2),
            "```",
            "</details>\n",
            "<details><summary>Output schema</summary>\n",
            "```json",
            json.dumps(tool["output_schema"], indent=2),
            "```",
            "</details>\n",
            "**Example invocation**",
            "",
            "```json",
            json.dumps({"tool": name, "arguments": args}, indent=2),
            "```",
            "",
            "**Example response** (long lists shortened)",
            "",
            "```json",
            json.dumps(shorten(response, 3), indent=2),
            "```",
            "",
        ]

    out = ROOT / "docs" / "mcp-tool-catalog.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    asyncio.run(main())
