"""Test setup: env vars, import paths and a simulator running on a free port."""

import os
import socket
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mcp-servers" / "alarm-management"))

TEST_TOKEN = "test-token"
os.environ["ALARM_API_TOKEN"] = TEST_TOKEN
os.environ["LLM_PROVIDER"] = "none"
os.environ["GROQ_API_KEY"] = ""
os.environ["MCP_SERVER_URL"] = ""
os.environ["ALARM_API_MAX_RETRIES"] = "2"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def simulator_url():
    """Runs the real simulator (FastAPI) in a background thread."""
    from apps.alarm_simulator.main import app

    port = free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{url}/health").status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    os.environ["ALARM_API_BASE_URL"] = url
    yield url
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def chaos(simulator_url):
    """Lets a test make the simulator fail on purpose; always resets afterwards."""
    headers = {"Authorization": f"Bearer {TEST_TOKEN}"}

    def set_chaos(**settings):
        httpx.post(f"{simulator_url}/admin/chaos", json=settings, headers=headers).raise_for_status()

    yield set_chaos
    httpx.post(f"{simulator_url}/admin/chaos", json={}, headers=headers)
