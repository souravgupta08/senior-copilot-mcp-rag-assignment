"""Contract tests for the Alarm Management API simulator (same contract as the Postman collections)."""

import pytest
from fastapi.testclient import TestClient

from apps.alarm_simulator.main import app

client = TestClient(app)
AUTH = {"Authorization": "Bearer test-token"}
RANGE = {"start_time": "2026-05-01T00:00:00Z", "end_time": "2026-07-01T00:00:00Z"}


def test_health_needs_no_auth():
    assert client.get("/health").json()["status"] == "ok"


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}])
def test_auth_is_required(headers):
    response = client.get("/assets/search", params={"query": "pump"}, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_trace_headers_are_echoed():
    response = client.get(
        "/assets/search", params={"query": "pump"}, headers={**AUTH, "trace_id": "trace-abc", "x-client-id": "pytest"}
    )
    assert response.headers["trace_id"] == "trace-abc"
    assert response.headers["x-client-id"] == "pytest"


def test_search_then_metadata_then_alarms_chain():
    asset_id = client.get("/assets/search", params={"query": "Boiler Feed Pump 101"}, headers=AUTH).json()["results"][
        0
    ]["asset_id"]
    assert asset_id == "AST-BFP-101"
    meta = client.get(f"/assets/{asset_id}/metadata", headers=AUTH).json()
    assert meta["related_assets"]
    alarms = client.get("/alarms", params={"asset_id": asset_id, "page_size": 5}, headers=AUTH).json()
    assert len(alarms["data"]) == 5
    alarm_id = alarms["data"][0]["alarm_id"]
    assert client.get(f"/alarms/{alarm_id}", headers=AUTH).json()["alarm_id"] == alarm_id


def test_pagination():
    page1 = client.get("/alarms", params={"site": "NorthPlant", "page": 1, "page_size": 10}, headers=AUTH).json()
    page2 = client.get("/alarms", params={"site": "NorthPlant", "page": 2, "page_size": 10}, headers=AUTH).json()
    assert page1["pagination"]["has_next"] is True
    assert {a["alarm_id"] for a in page1["data"]}.isdisjoint({a["alarm_id"] for a in page2["data"]})


def test_not_found_and_validation_errors():
    assert client.get("/alarms/ALM-999999", headers=AUTH).status_code == 404
    assert client.get("/assets/AST-XXX-000/metadata", headers=AUTH).status_code == 404
    bad = client.get("/alarms", params={"page_size": 9999}, headers=AUTH)
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "VALIDATION_ERROR"
    reversed_range = client.post(
        "/alarms/summary",
        headers=AUTH,
        json={"time_range": {"start_time": "2026-07-01T00:00:00Z", "end_time": "2026-05-01T00:00:00Z"}},
    )
    assert reversed_range.status_code == 400


@pytest.mark.parametrize(
    "path, body",
    [
        (
            "/alarms/summary",
            {
                "asset_ids": ["AST-BFP-101"],
                "time_range": RANGE,
                "group_by": ["alarm_name"],
                "kpis": ["alarm_count", "recurring_rate", "avg_ack_delay"],
            },
        ),
        (
            "/alarms/trends",
            {"asset_ids": ["AST-BFP-101"], "time_range": RANGE, "bucket": "daily", "metrics": ["alarm_count"]},
        ),
        ("/alarms/correlation", {"asset_ids": ["AST-BFP-101"], "time_range": RANGE, "min_support": 1}),
        ("/alarms/flood-analysis", {"unit": "Unit 2", "time_range": RANGE}),
        ("/alarms/rationalization-candidates", {"unit": "Unit 4", "time_range": RANGE, "recurrence_threshold": 8}),
    ],
)
def test_analytics_endpoints(path, body):
    response = client.post(path, json=body, headers=AUTH)
    assert response.status_code == 200, response.text


def test_priority_and_recommendations():
    alarm_id = client.get("/alarms", params={"site": "EastRefinery", "status": "active"}, headers=AUTH).json()["data"][
        0
    ]["alarm_id"]
    score = client.post("/alarms/priority-score", json={"alarm_id": alarm_id}, headers=AUTH).json()
    assert 0 <= score["priority_score"] <= 100
    recs = client.post("/recommendations/operator-actions", json={"alarm_id": alarm_id}, headers=AUTH).json()
    assert recs["recommended_actions"]


def test_calculation_generate_and_execute():
    filters = {"unit": "Unit 3", **RANGE}
    generated = client.post(
        "/calculation-code/generate", json={"calculation_type": "alarm_flood_index", "filters": filters}, headers=AUTH
    ).json()
    executed = client.post(
        "/calculation-code/execute",
        json={"calculation_id": generated["calculation_id"], "filters": filters},
        headers=AUTH,
    )
    assert executed.status_code == 200
    assert (
        client.post(
            "/calculation-code/generate", json={"calculation_type": "nope", "filters": filters}, headers=AUTH
        ).status_code
        == 400
    )
    assert client.get("/analytics/kpi-definitions", headers=AUTH).json()["kpis"]
