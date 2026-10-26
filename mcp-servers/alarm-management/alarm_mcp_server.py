"""Alarm Management MCP server.

python mcp-servers/alarm-management/alarm_mcp_server.py                     # stdio
MCP_TRANSPORT=streamable-http python mcp-servers/alarm-management/alarm_mcp_server.py  # :9000/mcp
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from pydantic import Field
from starlette.requests import Request
from starlette.responses import JSONResponse

# Make "connectors" (repo root) and "alarm_schemas" (this folder) importable
SERVER_DIR = Path(__file__).resolve().parent
ROOT_DIR = SERVER_DIR.parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(SERVER_DIR))

from alarm_schemas import (  # noqa: E402
    AlarmDetailResult,
    AlarmListResult,
    AlarmSummaryResult,
    AlarmTrendResult,
    AssetMetadataResult,
    AssetSearchResult,
    CorrelationResult,
    OperatorRecommendationResult,
    PriorityScoreResult,
)

from connectors.alarm_api_client import AlarmApiClient, AlarmApiError  # noqa: E402

load_dotenv()

# stdout is the MCP channel in stdio mode, so log to stderr
logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
logger = logging.getLogger("alarm-mcp")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("mcp").setLevel(logging.WARNING)

mcp = FastMCP(
    "Alarm Management MCP Server",
    instructions="Tools to investigate industrial alarms: find assets, read alarms, "
    "summaries, trends, correlation, priority scores and operator recommendations.",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("MCP_PORT", "9000")),
)

api = AlarmApiClient()


# =========================
# Reusable input types (validation happens automatically)
# =========================

AssetId = Annotated[str, Field(pattern=r"^AST-[A-Z]{3}-\d{3}$", description="Asset id, e.g. AST-BFP-101")]
AlarmId = Annotated[str, Field(pattern=r"^ALM-\d{6}$", description="Alarm id, e.g. ALM-000123")]
IsoTime = Annotated[
    str,
    Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", description="UTC timestamp, e.g. 2026-05-01T00:00:00Z"),
]
TraceId = Annotated[
    str | None, Field(default=None, max_length=64, description="Optional correlation id, forwarded to the API")
]
SeverityName = Literal["low", "medium", "high", "critical"]


# =========================
# Helpers
# =========================


def check_time_range(start_time: str, end_time: str):
    start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
    end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))
    if start >= end:
        raise ToolError("[INVALID_INPUT] start_time must be before end_time")


async def run_api_call(tool_name: str, coroutine):
    """
    Runs one API call, writes a structured log line and converts
    API errors into MCP ToolErrors (the client then gets isError=true).
    """
    started = time.perf_counter()
    outcome, status, attempts, trace_id = "error", None, 1, None
    try:
        data, meta = await coroutine
        outcome, status, attempts, trace_id = "success", meta["status_code"], meta["attempts"], meta["trace_id"]
        return data, meta
    except AlarmApiError as error:
        outcome, status, attempts, trace_id = "error", error.status_code, error.attempts, error.trace_id
        raise ToolError(str(error)) from error
    finally:
        logger.info(
            json.dumps(
                {
                    "service": "alarm-mcp",
                    "tool": tool_name,
                    "outcome": outcome,
                    "api_status": status,
                    "attempts": attempts,
                    "retries": max(0, attempts - 1),
                    "trace_id": trace_id,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        )


# =========================
# Tools
# =========================


@mcp.tool()
async def search_assets(
    query: Annotated[
        str, Field(min_length=2, max_length=100, description="Asset name or keyword, e.g. 'Boiler Feed Pump 101'")
    ],
    site: Annotated[str | None, Field(description="Optional site filter, e.g. NorthPlant")] = None,
    unit: Annotated[str | None, Field(description="Optional unit filter, e.g. 'Unit 1'")] = None,
    limit: Annotated[int, Field(ge=1, le=50)] = 5,
    trace_id: TraceId = None,
) -> AssetSearchResult:
    """Find assets by name or keyword and return their asset ids (best match first)."""
    data, meta = await run_api_call("search_assets", api.search_assets(query, site, unit, limit, trace_id))
    return AssetSearchResult(**data, meta=meta)


@mcp.tool()
async def get_asset_metadata(asset_id: AssetId, trace_id: TraceId = None) -> AssetMetadataResult:
    """Get asset details: type, criticality, operating limits, maintenance date and related assets."""
    data, meta = await run_api_call("get_asset_metadata", api.get_asset_metadata(asset_id, trace_id))
    return AssetMetadataResult(**data, meta=meta)


@mcp.tool()
async def get_alarms(
    asset_id: AssetId | None = None,
    site: str | None = None,
    unit: str | None = None,
    status: Literal["active", "acknowledged", "cleared"] | None = None,
    severity: list[SeverityName] | None = None,
    start_time: IsoTime | None = None,
    end_time: IsoTime | None = None,
    page: Annotated[int, Field(ge=1)] = 1,
    page_size: Annotated[int, Field(ge=1, le=200)] = 50,
    fetch_all_pages: Annotated[bool, Field(description="Follow pagination (max 5 pages)")] = False,
    sort_order: Literal["asc", "desc"] = "desc",
    trace_id: TraceId = None,
) -> AlarmListResult:
    """List alarms filtered by asset, site, unit, status, severity and time range (newest first)."""
    if not (asset_id or site or unit):
        raise ToolError("[INVALID_INPUT] Provide at least one of asset_id, site or unit")
    if start_time and end_time:
        check_time_range(start_time, end_time)

    params = {
        "asset_id": asset_id,
        "site": site,
        "unit": unit,
        "status": status,
        "severity": severity,
        "start_time": start_time,
        "end_time": end_time,
        "page": page,
        "page_size": page_size,
        "sort_by": "start_time",
        "sort_order": sort_order,
    }
    if fetch_all_pages:
        call = api.get_all_alarm_pages(params, trace_id=trace_id)
    else:
        call = api.get_alarms(params, trace_id=trace_id)
    data, meta = await run_api_call("get_alarms", call)
    return AlarmListResult(alarms=data["data"], pagination=data["pagination"], meta=meta)


@mcp.tool()
async def get_alarm_details(alarm_id: AlarmId, trace_id: TraceId = None) -> AlarmDetailResult:
    """Get one alarm by its id."""
    data, meta = await run_api_call("get_alarm_details", api.get_alarm(alarm_id, trace_id))
    return AlarmDetailResult(alarm=data, meta=meta)


@mcp.tool()
async def get_alarm_summary(
    start_time: IsoTime,
    end_time: IsoTime,
    asset_ids: Annotated[list[AssetId] | None, Field(max_length=20)] = None,
    site: str | None = None,
    unit: str | None = None,
    severity: list[SeverityName] | None = None,
    group_by: list[Literal["alarm_name", "alarm_code", "asset_id", "asset_name", "severity", "alarm_type"]] = [
        "alarm_name"
    ],
    kpis: list[Literal["alarm_count", "recurring_rate", "avg_ack_delay", "critical_count", "active_count"]] = [
        "alarm_count",
        "recurring_rate",
        "avg_ack_delay",
    ],
    trace_id: TraceId = None,
) -> AlarmSummaryResult:
    """Summarise alarms in a time range: counts, recurring rate and ack delay, grouped (e.g. by alarm name)."""
    check_time_range(start_time, end_time)
    body = {
        "asset_ids": asset_ids,
        "site": site,
        "unit": unit,
        "severity": severity,
        "time_range": {"start_time": start_time, "end_time": end_time},
        "group_by": group_by,
        "kpis": kpis,
    }
    data, meta = await run_api_call("get_alarm_summary", api.alarm_summary(body, trace_id))
    return AlarmSummaryResult(
        total_alarms=data["total_alarms"], overall=data["overall"], groups=data["groups"][:25], meta=meta
    )


@mcp.tool()
async def get_alarm_trends(
    start_time: IsoTime,
    end_time: IsoTime,
    asset_ids: Annotated[list[AssetId] | None, Field(max_length=20)] = None,
    site: str | None = None,
    unit: str | None = None,
    bucket: Literal["daily", "weekly"] = "weekly",
    severity: list[SeverityName] | None = None,
    trace_id: TraceId = None,
) -> AlarmTrendResult:
    """Alarm count per day/week and whether the trend is increasing, decreasing or flat."""
    check_time_range(start_time, end_time)
    body = {
        "asset_ids": asset_ids,
        "site": site,
        "unit": unit,
        "bucket": bucket,
        "severity": severity,
        "time_range": {"start_time": start_time, "end_time": end_time},
        "metrics": ["alarm_count", "critical_count"],
    }
    data, meta = await run_api_call("get_alarm_trends", api.alarm_trends(body, trace_id))
    return AlarmTrendResult(**data, meta=meta)


@mcp.tool()
async def correlate_alarms(
    asset_ids: Annotated[list[AssetId], Field(min_length=1, max_length=10)],
    start_time: IsoTime,
    end_time: IsoTime,
    lag_window_minutes: Annotated[int, Field(ge=1, le=120)] = 15,
    severity_threshold: SeverityName = "medium",
    min_support: Annotated[int, Field(ge=1, le=100)] = 2,
    trace_id: TraceId = None,
) -> CorrelationResult:
    """Find alarms that repeatedly happen together (on the assets and their related assets).
    Helps find likely causes."""
    check_time_range(start_time, end_time)
    body = {
        "asset_ids": asset_ids,
        "correlation_method": "cooccurrence",
        "time_range": {"start_time": start_time, "end_time": end_time},
        "lag_window_minutes": lag_window_minutes,
        "severity_threshold": severity_threshold,
        "min_support": min_support,
    }
    data, meta = await run_api_call("correlate_alarms", api.alarm_correlation(body, trace_id))
    return CorrelationResult(
        assets_in_scope=data["assets_in_scope"],
        events_analyzed=data["events_analyzed"],
        correlated_pairs=data["correlated_pairs"][:10],
        meta=meta,
    )


@mcp.tool()
async def score_alarm_priority(alarm_id: AlarmId, trace_id: TraceId = None) -> PriorityScoreResult:
    """Score how urgent an alarm is (0-100, P1-P4) and explain the factors."""
    data, meta = await run_api_call("score_alarm_priority", api.priority_score(alarm_id, trace_id))
    return PriorityScoreResult(**data, meta=meta)


@mcp.tool()
async def get_operator_recommendations(
    alarm_id: AlarmId,
    include_related: bool = True,
    include_asset_context: bool = True,
    include_historical_pattern: bool = True,
    trace_id: TraceId = None,
) -> OperatorRecommendationResult:
    """Get the API's recommended operator actions for an alarm plus related assets to check."""
    body = {
        "alarm_id": alarm_id,
        "include_related": include_related,
        "include_asset_context": include_asset_context,
        "include_historical_pattern": include_historical_pattern,
    }
    data, meta = await run_api_call("get_operator_recommendations", api.operator_recommendations(body, trace_id))
    return OperatorRecommendationResult(**data, meta=meta)


# =========================
# Health check (only for HTTP transport, used by docker compose)
# =========================


@mcp.custom_route("/health", methods=["GET"])
async def health(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "alarm-mcp-server"})


# Tools can be switched off with MCP_DISABLED_TOOLS=tool_a,tool_b
# (useful to demo how the copilot handles an unavailable tool)
for name in os.getenv("MCP_DISABLED_TOOLS", "").split(","):
    name = name.strip()
    if not name:
        continue
    try:
        mcp.remove_tool(name)
    except Exception:
        logger.warning(
            json.dumps({"service": "alarm-mcp", "event": "unknown_tool_in_MCP_DISABLED_TOOLS", "tool": name})
        )


if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    logger.info(
        json.dumps({"service": "alarm-mcp", "event": "starting", "transport": transport, "api_base_url": api.base_url})
    )
    mcp.run(transport=transport)
