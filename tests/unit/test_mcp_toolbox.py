"""
Unit tests for the copilot's MCP toolbox using a FAKE MCP session.
(The real stdio/HTTP connection is tested in tests/integration.)
"""

import asyncio
from types import SimpleNamespace

from apps.backend import mcp_client
from apps.backend.mcp_client import McpToolbox, build_server_config, shorten

SCHEMA = {
    "type": "object",
    "properties": {"alarm_id": {"type": "string", "pattern": "^ALM-\\d{6}$"}, "trace_id": {"type": "string"}},
    "required": ["alarm_id"],
}


def make_tool(name):
    return SimpleNamespace(name=name, description=f"{name} tool", inputSchema=SCHEMA, outputSchema={})


class FakeSession:
    def __init__(self, result=None, delay=0.0, raise_error=None):
        self.result = result
        self.delay = delay
        self.raise_error = raise_error
        self.calls = []

    async def list_tools(self):
        return SimpleNamespace(tools=[make_tool("score_alarm_priority")])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.raise_error:
            raise self.raise_error
        return self.result


def ok_result(data):
    return SimpleNamespace(isError=False, structuredContent=data, content=[])


async def ready_toolbox(session):
    toolbox = McpToolbox(session, trace_id="trace-test")
    await toolbox.discover()
    return toolbox


async def test_discovery_records_trace_step():
    toolbox = await ready_toolbox(FakeSession())
    assert "score_alarm_priority" in toolbox.tools
    assert toolbox.trace[0]["tool"] == "tools/list"


async def test_successful_call_adds_trace_id_and_records_attempts():
    data = {"alarm_id": "ALM-000001", "meta": {"attempts": 2, "status_code": 200, "trace_id": "trace-test"}}
    session = FakeSession(result=ok_result(data))
    toolbox = await ready_toolbox(session)

    result = await toolbox.call("score_alarm_priority", {"alarm_id": "ALM-000001"})

    assert result == data
    assert session.calls[0][1]["trace_id"] == "trace-test"  # trace metadata propagated
    step = toolbox.trace[-1]
    assert step["status"] == "success" and step["attempts"] == 2


async def test_missing_tool_is_reported_not_raised():
    toolbox = await ready_toolbox(FakeSession())
    assert await toolbox.call("delete_everything", {}) is None
    assert toolbox.trace[-1]["status"] == "unavailable"


async def test_invalid_arguments_are_caught_before_calling_server():
    session = FakeSession()
    toolbox = await ready_toolbox(session)
    assert await toolbox.call("score_alarm_priority", {"alarm_id": "not-an-id"}) is None
    assert toolbox.trace[-1]["status"] == "invalid_input"
    assert session.calls == []


async def test_tool_error_result_is_mapped():
    error = SimpleNamespace(
        isError=True,
        structuredContent=None,
        content=[SimpleNamespace(text="[NOT_FOUND] Alarm missing (status=404, attempts=1, trace_id=x)")],
    )
    toolbox = await ready_toolbox(FakeSession(result=error))
    assert await toolbox.call("score_alarm_priority", {"alarm_id": "ALM-000001"}) is None
    step = toolbox.trace[-1]
    assert step["status"] == "error" and "NOT_FOUND" in step["error"] and step["attempts"] == 1


async def test_timeout_is_handled(monkeypatch):
    monkeypatch.setattr(mcp_client, "TOOL_TIMEOUT_SECONDS", 0.05)
    toolbox = await ready_toolbox(FakeSession(delay=1))
    assert await toolbox.call("score_alarm_priority", {"alarm_id": "ALM-000001"}) is None
    assert toolbox.trace[-1]["status"] == "timeout"


async def test_connection_error_is_handled():
    toolbox = await ready_toolbox(FakeSession(raise_error=ConnectionError("gone")))
    assert await toolbox.call("score_alarm_priority", {"alarm_id": "ALM-000001"}) is None
    assert toolbox.trace[-1]["status"] == "error"


def test_server_config_switches_transport(monkeypatch):
    monkeypatch.setenv("MCP_SERVER_URL", "http://alarm-mcp:9000")
    assert build_server_config()["alarm_management"] == {
        "transport": "streamable_http",
        "url": "http://alarm-mcp:9000/mcp",
    }
    monkeypatch.setenv("MCP_SERVER_URL", "")
    assert build_server_config()["alarm_management"]["transport"] == "stdio"


def test_shorten_cuts_long_lists():
    short = shorten({"rows": list(range(40))}, max_items=5)
    assert len(short["rows"]) == 6 and "35 more" in short["rows"][-1]
