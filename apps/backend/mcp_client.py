"""
MCP client for the copilot.

The copilot NEVER calls the Alarm API directly. It talks to our
Alarm Management MCP server, which then calls the API.

Two ways to reach the MCP server:
- MCP_SERVER_URL set     -> streamable HTTP (used in docker compose)
- MCP_SERVER_URL empty   -> stdio: we start the server script as a child process (local dev / tests)
"""

import asyncio
import json
import os
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from jsonschema import Draft202012Validator
from langchain_mcp_adapters.client import MultiServerMCPClient

load_dotenv()

ROOT_DIR = Path(__file__).resolve().parents[2]
SERVER_SCRIPT = ROOT_DIR / "mcp-servers" / "alarm-management" / "alarm_mcp_server.py"
SERVER_NAME = "alarm_management"
TOOL_TIMEOUT_SECONDS = float(os.getenv("MCP_TOOL_TIMEOUT_SECONDS", "30"))


def build_server_config() -> dict:
    url = os.getenv("MCP_SERVER_URL", "").strip()
    if url:
        if not url.rstrip("/").endswith("/mcp"):
            url = url.rstrip("/") + "/mcp"
        return {SERVER_NAME: {"transport": "streamable_http", "url": url}}

    env = os.environ.copy()
    env["MCP_TRANSPORT"] = "stdio"
    return {
        SERVER_NAME: {
            "transport": "stdio",
            "command": sys.executable,  # same Python that runs the copilot
            "args": [str(SERVER_SCRIPT)],
            "env": env,
        }
    }


def shorten(value, max_items: int = 15):
    """Keep raw responses readable in the GUI: long lists are cut."""
    if isinstance(value, list):
        items = [shorten(v, max_items) for v in value[:max_items]]
        if len(value) > max_items:
            items.append(f"... {len(value) - max_items} more item(s) not shown")
        return items
    if isinstance(value, dict):
        return {k: shorten(v, max_items) for k, v in value.items()}
    return value


class McpToolbox:
    """
    Wraps one open MCP session and records every step for the GUI trace.
    """

    def __init__(self, session, trace_id: str, server_name: str = SERVER_NAME):
        self.session = session
        self.trace_id = trace_id
        self.server_name = server_name
        self.tools = {}  # name -> tool definition (with input/output schema)
        self.trace = []  # list of executed steps

    # ---------- discovery ----------

    async def discover(self) -> list[dict]:
        started = time.perf_counter()
        result = await self.session.list_tools()
        self.tools = {tool.name: tool for tool in result.tools}
        self.trace.append(
            {
                "step": len(self.trace) + 1,
                "server": self.server_name,
                "tool": "tools/list",
                "status": "success",
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "request": {},
                "response": {"tools": sorted(self.tools)},
                "attempts": 1,
                "trace_id": self.trace_id,
            }
        )
        return self.describe_tools()

    def describe_tools(self) -> list[dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.inputSchema,
                "output_schema": tool.outputSchema,
            }
            for tool in self.tools.values()
        ]

    # ---------- invocation ----------

    def validate_arguments(self, tool, arguments: dict) -> list[str]:
        """Schema-aware check BEFORE calling the server (catches bad inputs early)."""
        validator = Draft202012Validator(tool.inputSchema)
        return [
            f"{'.'.join(str(p) for p in e.path) or 'arguments'}: {e.message}" for e in validator.iter_errors(arguments)
        ]

    async def call(self, tool_name: str, arguments: dict, purpose: str = "") -> dict | None:
        """
        Calls one MCP tool. Never raises: problems are written into the trace
        and None is returned, so the workflow can continue with partial results.
        """
        step = {
            "step": len(self.trace) + 1,
            "server": self.server_name,
            "tool": tool_name,
            "purpose": purpose,
            "request": arguments,
            "trace_id": self.trace_id,
            "attempts": 0,
        }
        self.trace.append(step)
        started = time.perf_counter()

        tool = self.tools.get(tool_name)
        if tool is None:
            step.update(
                status="unavailable",
                duration_ms=0,
                error=f"Tool '{tool_name}' is not offered by the MCP server. Available: {sorted(self.tools)}",
            )
            return None

        arguments = {k: v for k, v in arguments.items() if v is not None}
        if "trace_id" in tool.inputSchema.get("properties", {}):
            arguments["trace_id"] = self.trace_id
        step["request"] = arguments

        errors = self.validate_arguments(tool, arguments)
        if errors:
            step.update(status="invalid_input", duration_ms=0, error="; ".join(errors))
            return None

        try:
            result = await asyncio.wait_for(
                self.session.call_tool(tool_name, arguments),
                timeout=TOOL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            step.update(status="timeout", error=f"No answer within {TOOL_TIMEOUT_SECONDS}s")
            return None
        except Exception as error:  # connection dropped, protocol error ...
            step.update(status="error", error=f"{type(error).__name__}: {error}")
            return None
        finally:
            step["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)

        if result.isError:
            text = " ".join(getattr(c, "text", "") for c in result.content)
            step.update(status="error", error=text[:500])
            # the server puts "attempts=N" in its error text
            if "attempts=" in text:
                try:
                    step["attempts"] = int(text.split("attempts=")[1].split(",")[0].split(")")[0])
                except ValueError:
                    pass
            return None

        data = result.structuredContent
        if data is None:  # older servers only send text
            try:
                data = json.loads(result.content[0].text)
            except (IndexError, AttributeError, ValueError):
                step.update(status="error", error="Tool returned a response that is not JSON")
                return None
        meta = data.get("meta", {})
        step.update(
            status="success",
            attempts=meta.get("attempts", 1),
            api_status=meta.get("status_code"),
            response=shorten(data),
        )
        return data


@asynccontextmanager
async def open_toolbox(trace_id: str):
    """
    Usage:
        async with open_toolbox("trace-123") as toolbox:
            await toolbox.discover()
            data = await toolbox.call("search_assets", {"query": "Boiler Feed Pump 101"})
    """
    client = MultiServerMCPClient(build_server_config())
    async with client.session(SERVER_NAME) as session:
        yield McpToolbox(session, trace_id)


async def list_server_tools() -> list[dict]:
    """Used by the GUI 'Tool discovery' panel."""
    async with open_toolbox("discovery") as toolbox:
        return await toolbox.discover()
