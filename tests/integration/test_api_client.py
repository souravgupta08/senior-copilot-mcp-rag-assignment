"""
Tests for the HTTP connector used by the MCP server:
auth + trace headers, retries, timeouts, error mapping, pagination.
httpx.MockTransport lets us fake any API behaviour without a server.
"""

import httpx
import pytest

from connectors.alarm_api_client import AlarmApiClient, AlarmApiError


def make_client(handler, retries=2):
    return AlarmApiClient(
        base_url="http://api.test",
        token="secret-token",
        max_retries=retries,
        backoff_seconds=0,
        transport=httpx.MockTransport(handler),
    )


async def test_sends_auth_and_trace_headers():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json={"results": []}, headers={"trace_id": request.headers["trace_id"]})

    data, meta = await make_client(handler).search_assets("pump", trace_id="trace-42")
    assert seen["authorization"] == "Bearer secret-token"
    assert seen["trace_id"] == "trace-42" and seen["x-client-id"] == "alarm-mcp-server"
    assert meta == {"trace_id": "trace-42", "status_code": 200, "attempts": 1, "duration_ms": meta["duration_ms"]}


async def test_retries_on_503_then_succeeds():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503, json={"error": {"message": "busy"}})
        return httpx.Response(200, json={"ok": True})

    data, meta = await make_client(handler).get_alarm("ALM-000001")
    assert data == {"ok": True}
    assert meta["attempts"] == 3


async def test_gives_up_after_max_retries():
    def handler(request):
        return httpx.Response(503, json={"error": {"message": "down"}})

    with pytest.raises(AlarmApiError) as error:
        await make_client(handler, retries=1).get_alarm("ALM-000001")
    assert error.value.code == "UPSTREAM_ERROR"
    assert error.value.attempts == 2


async def test_does_not_retry_404_and_maps_error():
    calls = {"n": 0}

    def handler(request):
        calls["n"] += 1
        return httpx.Response(404, json={"error": {"code": "NOT_FOUND", "message": "Alarm 'X' not found"}})

    with pytest.raises(AlarmApiError) as error:
        await make_client(handler).get_alarm("X")
    assert calls["n"] == 1
    assert error.value.code == "NOT_FOUND"
    assert "secret-token" not in str(error.value)  # secrets never leak into errors


@pytest.mark.parametrize("status, code", [(401, "AUTH_FAILED"), (422, "INVALID_INPUT"), (400, "INVALID_INPUT")])
async def test_error_mapping(status, code):
    def handler(request):
        return httpx.Response(
            status, json={"error": {"message": "nope", "details": [{"field": "x", "message": "bad"}]}}
        )

    with pytest.raises(AlarmApiError) as error:
        await make_client(handler).get_alarm("X")
    assert error.value.code == code


async def test_timeout_is_retried_and_mapped():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(AlarmApiError) as error:
        await make_client(handler, retries=1).get_alarm("X")
    assert error.value.code == "TIMEOUT" and error.value.attempts == 2


async def test_connection_error_is_mapped():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(AlarmApiError) as error:
        await make_client(handler, retries=0).get_alarm("X")
    assert error.value.code == "CONNECTION_FAILED"


async def test_follows_pagination():
    def handler(request):
        page = int(request.url.params["page"])
        return httpx.Response(
            200,
            json={
                "data": [{"alarm_id": f"ALM-00000{page}"}],
                "pagination": {"page": page, "page_size": 1, "total": 3, "total_pages": 3, "has_next": page < 3},
            },
        )

    data, meta = await make_client(handler).get_all_alarm_pages({"site": "X", "page_size": 1})
    assert [a["alarm_id"] for a in data["data"]] == ["ALM-000001", "ALM-000002", "ALM-000003"]
    assert meta["pages_fetched"] == 3 and data["pagination"]["truncated"] is False


async def test_against_real_simulator(simulator_url):
    client = AlarmApiClient(base_url=simulator_url, token="test-token")
    data, meta = await client.search_assets("Boiler Feed Pump 101")
    assert data["results"][0]["asset_id"] == "AST-BFP-101"
    with pytest.raises(AlarmApiError) as error:
        await AlarmApiClient(base_url=simulator_url, token="wrong").search_assets("pump")
    assert error.value.code == "AUTH_FAILED"


async def test_retries_any_5xx_and_honours_retry_after(monkeypatch):
    waits = []

    async def fake_sleep(seconds):
        waits.append(seconds)

    monkeypatch.setattr("connectors.alarm_api_client.asyncio.sleep", fake_sleep)
    responses = iter(
        [
            httpx.Response(500, json={"error": {"message": "boom"}}),
            httpx.Response(429, json={"error": {"message": "slow down"}}, headers={"Retry-After": "2"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    data, meta = await make_client(lambda request: next(responses)).get_alarm("ALM-000001")
    assert meta["attempts"] == 3
    assert waits[1] == 2.0
