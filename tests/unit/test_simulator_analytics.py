"""Unit tests for the simulator's business logic (no web server needed)."""

from datetime import datetime, timezone

from apps.alarm_simulator import analytics
from apps.alarm_simulator.data import ASSETS_BY_ID, build_alarms, parse_time

NOW = datetime(2026, 10, 26, 12, 0, tzinfo=timezone.utc)
ALARMS = build_alarms(now=NOW)
START, END = parse_time("2026-07-28T00:00:00Z"), parse_time("2026-10-26T12:00:00Z")


def test_data_is_deterministic():
    assert build_alarms(now=NOW) == ALARMS


def test_active_alarms_exist_for_demo_assets():
    active = {a["asset_id"] for a in ALARMS if a["status"] == "active"}
    assert {"AST-BFP-101", "AST-BFP-102", "AST-GCK-501"} <= active


def test_search_exact_name_ranks_first():
    results = analytics.search_assets("Boiler Feed Pump 101")
    assert results[0]["asset_id"] == "AST-BFP-101"
    assert results[0]["match_score"] == 1.0


def test_search_by_equipment_type_prefers_that_type():
    results = analytics.search_assets("compressor")
    top = [r for r in results if r["match_score"] == results[0]["match_score"]]
    assert all(r["asset_type"] == "compressor" for r in top)


def test_search_with_unit_filter():
    results = analytics.search_assets("motor", unit="Unit 5")
    assert results and all(r["unit"] == "Unit 5" for r in results)


def test_paginate():
    items, page = analytics.paginate(list(range(23)), page=3, page_size=10)
    assert items == [20, 21, 22]
    assert page["total_pages"] == 3 and page["has_next"] is False


def test_compute_kpis():
    rows = analytics.filter_alarms(ALARMS, asset_ids=["AST-BFP-101"], start_time=START, end_time=END)
    kpis = analytics.compute_kpis(rows, ["alarm_count", "recurring_rate", "critical_count"])
    assert kpis["alarm_count"] == len(rows) > 0
    assert 0 <= kpis["recurring_rate"] <= 1


def test_correlation_finds_valve_before_pump_pattern():
    rows = analytics.filter_alarms(ALARMS, start_time=START, end_time=END)
    result = analytics.correlate(rows, ["AST-BFP-101"], 15, "medium", 2)
    top = result["correlated_pairs"][0]
    assert top["leading_alarm"]["asset_id"] == "AST-FCV-101"
    assert top["following_alarm"]["alarm_name"] == "High Discharge Pressure"
    assert "AST-FCV-101" in result["assets_in_scope"]  # related assets are included


def test_flood_analysis_detects_unit2_floods():
    rows = analytics.filter_alarms(ALARMS, unit="Unit 2", start_time=START, end_time=END)
    result = analytics.flood_analysis(rows, 10, 10, START, END)
    assert result["flood_count"] >= 1
    assert result["flood_windows"][0]["alarm_count"] >= 10


def test_priority_score_for_critical_active_alarm_is_p1():
    alarm = next(a for a in ALARMS if a["asset_id"] == "AST-BFP-101" and a["status"] == "active")
    result = analytics.priority_score(alarm, ALARMS)
    assert result["priority_level"] == "P1"
    assert {f["factor"] for f in result["factors"]} >= {"severity", "asset_criticality"}


def test_recommendations_use_equipment_specific_rules():
    pump = next(a for a in ALARMS if a["asset_id"] == "AST-BFP-101" and a["alarm_name"] == "High Discharge Pressure")
    comp = next(a for a in ALARMS if a["asset_id"] == "AST-GCK-501" and a["alarm_name"] == "High Discharge Pressure")
    pump_text = " ".join(x["action"] for x in analytics.operator_recommendations(pump, ALARMS)["recommended_actions"])
    comp_text = " ".join(x["action"] for x in analytics.operator_recommendations(comp, ALARMS)["recommended_actions"])
    assert "restart the pump" in pump_text
    assert "cooler" in comp_text


def test_related_assets_in_metadata():
    meta = analytics.asset_metadata("AST-BFP-101")
    names = {r["asset_name"] for r in meta["related_assets"]}
    assert "Feedwater Control Valve FCV-101" in names
    assert meta["asset_type"] == ASSETS_BY_ID["AST-BFP-101"]["asset_type"]


def test_generate_and_execute_calculation():
    calc = analytics.generate_calculation("operator_response_efficiency", {"site": "SouthPlant"})
    rows = analytics.filter_alarms(ALARMS, site="SouthPlant", start_time=START, end_time=END)
    result = analytics.execute_calculation(calc["calculation_id"], rows, START, END)
    assert 0 <= result["result"]["value"] <= 100
    assert result["result"]["unit"] == "%"


def test_search_by_asset_id_or_tag_picks_that_asset():
    assert analytics.search_assets("AST-BFP-101")[0]["asset_id"] == "AST-BFP-101"
    assert analytics.search_assets("BFP-101")[0]["asset_id"] == "AST-BFP-101"


def test_correlation_confidence_never_above_one():
    rows = analytics.filter_alarms(ALARMS, start_time=START, end_time=END)
    for asset_id in ("AST-SDR-201", "AST-BFP-101", "AST-GCK-501"):
        result = analytics.correlate(rows, [asset_id], 15, "low", 1)
        assert all(p["confidence"] <= 1 for p in result["correlated_pairs"])
