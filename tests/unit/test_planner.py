"""Unit tests for intent detection and entity extraction (tool selection)."""

from datetime import datetime, timezone

import pytest

from apps.backend.planner import detect_intent, extract_asset_query, extract_days, extract_severity, make_plan

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "question, intent",
    [
        ("Show active critical alarms for Boiler Feed Pump 102 and recommend immediate actions.", "active_alarms"),
        ("Why are compressor discharge pressure alarms repeatedly occurring?", "recurring_causes"),
        ("Which alarm has the highest priority in EastRefinery, and why?", "highest_priority"),
        ("What related assets should be inspected for this motor trip alarm?", "related_assets"),
        ("Which operating procedure applies to this alarm?", "procedure"),
        ("Are the API recommendations consistent with the maintenance manual?", "consistency"),
        ("Investigate recurring high-severity alarms for Boiler Feed Pump 101 over the last 90 days", "investigation"),
    ],
)
def test_detect_intent(question, intent):
    assert detect_intent(question) == intent


@pytest.mark.parametrize(
    "question, asset",
    [
        ("Investigate Boiler Feed Pump 101 alarms", "Boiler Feed Pump 101"),
        ("Show active alarms for Boiler Feed Pump 102 and recommend actions", "Boiler Feed Pump 102"),
        ("Investigate Gas Compressor K-501", "Gas Compressor K-501"),
        ("check K-501 please", "K-501"),
        ("Why are compressor discharge pressure alarms repeated?", "compressor"),
        ("Investigate Pump XYZ 999", "Pump XYZ 999"),
        ("Check the Flowserve pump pressure switch bulletin for Boiler Feed Pump 101", "Boiler Feed Pump 101"),
        ("Is Pump 101 OK?", "Pump 101"),
        ("Check pump P-101 SOP", "pump P-101"),
        ("alarms on pump 101, last 30 days", "pump 101"),
        ("Which alarm has the highest priority in EastRefinery?", None),
    ],
)
def test_extract_asset_query(question, asset):
    assert extract_asset_query(question) == asset


def test_extract_days_and_severity():
    assert extract_days("over the last 90 days") == (90, True, None)
    assert extract_days("past 2 weeks") == (14, True, None)
    assert extract_days("no range") == (90, False, None)
    assert extract_days("last 2 years")[0] == 365 and "limited" in extract_days("last 2 years")[2]
    assert extract_days("last 0 days")[0] == 1
    assert extract_severity("recurring high-severity alarms") == ["high", "critical"]
    assert extract_severity("active critical alarms") == ["critical"]
    assert extract_severity("all alarms") is None


def test_plan_for_acceptance_scenario_builds_time_range_and_steps():
    plan = make_plan(
        "Investigate recurring high-severity alarms for Boiler Feed Pump 101 over the last 90 days", now=NOW
    )
    assert plan["intent"] == "investigation"
    assert plan["asset_query"] == "Boiler Feed Pump 101"
    assert plan["start_time"] == "2026-07-28T12:00:00Z"
    assert plan["end_time"] == "2026-10-26T12:00:00Z"
    assert plan["steps"][-1] == "rag"
    assert {"alarms", "correlation", "priority", "recommendations"} <= set(plan["steps"])
    assert plan["assumptions"] == []


def test_plan_site_scope_and_active_status():
    plan = make_plan("Which alarm has the highest priority in EastRefinery, and why?", now=NOW)
    assert plan["site"] == "EastRefinery"
    assert plan["status"] == "active"
    assert "priority" in plan["steps"]


def test_follow_up_question_reuses_context():
    context = {
        "assets": [{"asset_id": "AST-BFP-101", "asset_name": "Boiler Feed Pump 101", "asset_type": "pump"}],
        "alarm_id": "ALM-000010",
    }
    plan = make_plan("Which operating procedure applies to this alarm?", context, now=NOW)
    assert plan["use_context_assets"] is True
    assert plan["alarm_id"] == "ALM-000010"
    assert any("previous question" in a for a in plan["assumptions"])


def test_off_topic_message_is_flagged():
    plan = make_plan("hello there", {"assets": [{"asset_name": "x", "asset_type": "pump"}]}, now=NOW)
    assert plan["off_topic"] is True
    assert plan["use_context_assets"] is False


def test_unit_is_normalised():
    assert make_plan("alarms in unit2", now=NOW)["unit"] == "Unit 2"
    assert make_plan("alarms in Unit 4 last week", now=NOW)["unit"] == "Unit 4"
