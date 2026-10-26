"""
MCP server tests: tool registration, discovery, schemas, validation,
error mapping and trace propagation. The server runs in-process.
"""

import alarm_mcp_server as server
import httpx
import pytest
from mcp.server.fastmcp.exceptions import ToolError

from connectors.alarm_api_client import AlarmApiClient

EXPECTED_TOOLS = {
    "search_assets",
    "get_asset_metadata",
    "get_alarms",
    "get_alarm_details",
    "get_alarm_summary",
    "get_alarm_trends",
    "correlate_alarms",
    "score_alarm_priority",
    "get_operator_recommendations",
}
RANGE = {"start_time": "2026-05-01T00:00:00Z", "end_time": "2026-07-01T00:00:00Z"}


@pytest.fixture
def live_api(simulator_url, monkeypatch):
    monkeypatch.setattr(server, "api", AlarmApiClient(base_url=simulator_url, token="test-token"))


def structured(result):
    """FastMCP.call_tool returns (content, structured_output)."""
    return result[1]


async def test_all_tools_are_registered_with_schemas():
    tools = {t.name: t for t in await server.mcp.list_tools()}
    assert EXPECTED_TOOLS <= set(tools)
    for tool in tools.values():
        assert tool.description
        assert tool.inputSchema["type"] == "object"
        assert tool.outputSchema and "meta" in tool.outputSchema["properties"]


async def test_input_validation_rejects_bad_ids():
    with pytest.raises(ToolError, match="pattern"):
        await server.mcp.call_tool("get_asset_metadata", {"asset_id": "bad-id"})
    with pytest.raises(ToolError):
        await server.mcp.call_tool("correlate_alarms", {"asset_ids": [], **RANGE})


async def test_business_validation(live_api):
    with pytest.raises(ToolError, match="start_time must be before"):
        await server.mcp.call_tool(
            "get_alarm_summary", {"start_time": RANGE["end_time"], "end_time": RANGE["start_time"]}
        )
    with pytest.raises(ToolError, match="at least one"):
        await server.mcp.call_tool("get_alarms", {})


async def test_search_and_chain_through_tools(live_api):
    search = structured(await server.mcp.call_tool("search_assets", {"query": "Boiler Feed Pump 101"}))
    asset_id = search["results"][0]["asset_id"]
    alarms = structured(await server.mcp.call_tool("get_alarms", {"asset_id": asset_id, "page_size": 5}))
    alarm_id = alarms["alarms"][0]["alarm_id"]
    recs = structured(await server.mcp.call_tool("get_operator_recommendations", {"alarm_id": alarm_id}))
    assert recs["asset_id"] == asset_id
    assert recs["meta"]["status_code"] == 200


async def test_pagination_through_tool(live_api):
    result = structured(
        await server.mcp.call_tool("get_alarms", {"site": "NorthPlant", "page_size": 20, "fetch_all_pages": True})
    )
    assert result["meta"]["pages_fetched"] == 5
    assert len(result["alarms"]) == 100
    assert result["pagination"]["truncated"] is True


async def test_api_errors_become_tool_errors(live_api):
    with pytest.raises(ToolError, match="NOT_FOUND"):
        await server.mcp.call_tool("get_asset_metadata", {"asset_id": "AST-XXX-999"})


async def test_auth_failure_is_mapped_and_token_not_exposed(simulator_url, monkeypatch):
    monkeypatch.setattr(server, "api", AlarmApiClient(base_url=simulator_url, token="leaky-secret"))
    with pytest.raises(ToolError) as error:
        await server.mcp.call_tool("search_assets", {"query": "pump"})
    assert "AUTH_FAILED" in str(error.value)
    assert "leaky-secret" not in str(error.value)


async def test_retry_on_upstream_failure_is_visible(simulator_url, monkeypatch):
    calls = {"n": 0}

    def flaky(request):
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return httpx.Response(
            200,
            json={
                "alarm_id": "ALM-000001",
                "priority_score": 50,
                "priority_level": "P3",
                "factors": [],
                "explanation": "x",
            },
        )

    monkeypatch.setattr(
        server,
        "api",
        AlarmApiClient(base_url="http://x", token="t", backoff_seconds=0, transport=httpx.MockTransport(flaky)),
    )
    result = structured(await server.mcp.call_tool("score_alarm_priority", {"alarm_id": "ALM-000001"}))
    assert result["meta"]["attempts"] == 2


async def test_trace_id_is_forwarded_to_api(monkeypatch):
    seen = {}

    def handler(request):
        seen["trace"] = request.headers.get("trace_id")
        return httpx.Response(
            200,
            json={
                "query": "p",
                "results": [],
                "pagination": {"page": 1, "page_size": 5, "total": 0, "total_pages": 1, "has_next": False},
            },
            headers={"trace_id": request.headers.get("trace_id")},
        )

    monkeypatch.setattr(
        server, "api", AlarmApiClient(base_url="http://x", token="t", transport=httpx.MockTransport(handler))
    )
    result = structured(await server.mcp.call_tool("search_assets", {"query": "pump", "trace_id": "trace-xyz"}))
    assert seen["trace"] == "trace-xyz"
    assert result["meta"]["trace_id"] == "trace-xyz"


async def test_health_route_registered():
    paths = [route.path for route in server.mcp._custom_starlette_routes]
    assert "/health" in paths


def test_unknown_disabled_tool_does_not_crash_server(monkeypatch):
    import importlib

    monkeypatch.setenv("MCP_DISABLED_TOOLS", "get_alarm_details, not_a_tool, ")
    module = importlib.reload(server)
    try:
        names = {t.name for t in module.mcp._tool_manager.list_tools()}
        assert "get_alarm_details" not in names and "search_assets" in names
    finally:
        monkeypatch.setenv("MCP_DISABLED_TOOLS", "")
        importlib.reload(server)
