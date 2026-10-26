"""
MCP client integration: the copilot starts the REAL MCP server (stdio)
and talks to it with the MCP protocol.
"""

from apps.backend.mcp_client import list_server_tools, open_toolbox


async def test_connect_and_discover_tools(simulator_url):
    tools = await list_server_tools()
    names = {t["name"] for t in tools}
    assert {"search_assets", "get_alarms", "correlate_alarms", "get_operator_recommendations"} <= names
    assert all(t["input_schema"] and t["output_schema"] for t in tools)


async def test_invoke_chain_invalid_args_and_missing_tool(simulator_url):
    async with open_toolbox("trace-int-1") as toolbox:
        await toolbox.discover()

        search = await toolbox.call("search_assets", {"query": "Gas Compressor K-501"})
        asset_id = search["results"][0]["asset_id"]
        alarms = await toolbox.call("get_alarms", {"asset_id": asset_id, "status": "active"})
        alarm_id = alarms["alarms"][0]["alarm_id"]
        score = await toolbox.call("score_alarm_priority", {"alarm_id": alarm_id})  # output -> input
        assert score["alarm_id"] == alarm_id

        assert await toolbox.call("score_alarm_priority", {"alarm_id": "nope"}) is None
        assert await toolbox.call("create_ticket", {"title": "x"}) is None

    statuses = [s["status"] for s in toolbox.trace]
    assert statuses == ["success", "success", "success", "success", "invalid_input", "unavailable"]
    assert all(s["trace_id"] == "trace-int-1" for s in toolbox.trace)


async def test_partial_failure_from_api(simulator_url, chaos):
    chaos(fail_paths=["/alarms/correlation"])
    async with open_toolbox("trace-int-2") as toolbox:
        await toolbox.discover()
        ok = await toolbox.call("search_assets", {"query": "Boiler Feed Pump 101"})
        failed = await toolbox.call(
            "correlate_alarms",
            {"asset_ids": ["AST-BFP-101"], "start_time": "2026-05-01T00:00:00Z", "end_time": "2026-07-01T00:00:00Z"},
        )
    assert ok is not None and failed is None
    step = toolbox.trace[-1]
    assert step["status"] == "error"
    assert step["attempts"] == 3  # first try + 2 retries
    assert "UPSTREAM_ERROR" in step["error"]
