"""
Business logic of the Alarm Management API simulator.

Every function here takes plain Python data and returns plain dicts,
so it is easy to unit test without starting a web server.
"""

import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from apps.alarm_simulator.data import ASSETS, ASSETS_BY_ID, SEVERITY_ORDER, parse_time, to_iso

# =========================
# Filtering
# =========================


def filter_alarms(
    alarms,
    asset_ids=None,
    site=None,
    unit=None,
    status=None,
    severity=None,
    alarm_types=None,
    start_time=None,
    end_time=None,
):
    """Return only alarms that match all given filters (None = no filter)."""
    result = []
    severity = [s.lower() for s in severity] if severity else None
    alarm_types = [t.lower() for t in alarm_types] if alarm_types else None

    for alarm in alarms:
        if asset_ids and alarm["asset_id"] not in asset_ids:
            continue
        if site and alarm["site"].lower() != site.lower():
            continue
        if unit and alarm["unit"].lower() != unit.lower():
            continue
        if status and alarm["status"] != status.lower():
            continue
        if severity and alarm["severity"] not in severity:
            continue
        if alarm_types and alarm["alarm_type"] not in alarm_types:
            continue
        start = parse_time(alarm["start_time"])
        if start_time and start < start_time:
            continue
        if end_time and start > end_time:
            continue
        result.append(alarm)
    return result


def paginate(items, page, page_size):
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    begin = (page - 1) * page_size
    return items[begin : begin + page_size], {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "has_next": page < total_pages,
    }


# =========================
# Asset search
# =========================


def search_assets(query, site=None, unit=None):
    """
    Very simple search: split the query into words and score each asset by
    how many words appear in its name / type / id.
    """
    words = [w for w in query.lower().replace("-", " ").split() if w]
    results = []

    for asset in ASSETS:
        if site and asset["site"].lower() != site.lower():
            continue
        if unit and asset["unit"].lower() != unit.lower():
            continue

        haystack = f"{asset['asset_name']} {asset['asset_type']} {asset['asset_id']}".lower().replace("-", " ")
        tokens = haystack.replace("_", " ").split()
        # short words (like "k" in "K-501") must match a whole token, longer words can match part of a word
        matched = sum(1 for w in words if w in tokens or (len(w) > 2 and w in haystack))
        if matched == 0:
            continue

        # 80% for matched words + 20% bonus when the query names the asset type ("compressor")
        score = 0.8 * matched / len(words)
        if asset["asset_type"] in words:
            score += 0.2
        id_tokens = asset["asset_id"].lower().replace("-", " ").split()
        # an exact name, or a query made only of id parts ("AST-BFP-101", "BFP-101"), is a perfect match
        if asset["asset_name"].lower() == query.lower().strip() or all(w in id_tokens for w in words):
            score = 1.0
        name_hits = sum(1 for w in words if w in asset["asset_name"].lower())
        results.append(
            {
                "asset_id": asset["asset_id"],
                "asset_name": asset["asset_name"],
                "asset_type": asset["asset_type"],
                "site": asset["site"],
                "unit": asset["unit"],
                "criticality": asset["criticality"],
                "match_score": round(score, 2),
                "_name_hits": name_hits,
            }
        )

    # ties: prefer assets whose NAME contains more of the query words, then alphabetical
    results.sort(key=lambda r: (-r["match_score"], -r["_name_hits"], r["asset_name"]))
    for r in results:
        r.pop("_name_hits")
    return results


def asset_metadata(asset_id):
    asset = ASSETS_BY_ID[asset_id]
    related = []
    for rel in asset["related_assets"]:
        other = ASSETS_BY_ID[rel["asset_id"]]
        related.append(
            {
                "asset_id": other["asset_id"],
                "asset_name": other["asset_name"],
                "asset_type": other["asset_type"],
                "relationship": rel["relationship"],
            }
        )
    data = {key: value for key, value in asset.items() if key != "related_assets"}
    data["related_assets"] = related
    return data


# =========================
# KPIs used by summary / trends
# =========================


def _is_recurring(alarm, history):
    """An alarm 'recurs' if the same alarm fired on the same asset in the previous 24 hours."""
    key = (alarm["asset_id"], alarm["alarm_name"])
    start = parse_time(alarm["start_time"])
    previous = history.get(key)
    history[key] = start
    return previous is not None and (start - previous) <= timedelta(hours=24)


def compute_kpis(alarms, kpis):
    alarms = sorted(alarms, key=lambda x: x["start_time"])
    count = len(alarms)
    result = {}
    history = {}
    recurring = sum(1 for a in alarms if _is_recurring(a, history))
    ack_delays = [a["ack_delay_seconds"] for a in alarms if a["ack_delay_seconds"] is not None]
    fleeting = [a for a in alarms if a["duration_seconds"] is not None and a["duration_seconds"] < 60]

    for kpi in kpis:
        if kpi == "alarm_count":
            result[kpi] = count
        elif kpi == "recurring_rate":
            result[kpi] = round(recurring / count, 3) if count else 0.0
        elif kpi == "avg_ack_delay":
            result[kpi] = round(sum(ack_delays) / len(ack_delays), 1) if ack_delays else None
        elif kpi == "critical_count":
            result[kpi] = sum(1 for a in alarms if a["severity"] == "critical")
        elif kpi == "active_count":
            result[kpi] = sum(1 for a in alarms if a["status"] == "active")
        elif kpi == "suppression_candidate_rate":
            result[kpi] = round(len(fleeting) / count, 3) if count else 0.0
    return result


SUPPORTED_KPIS = [
    "alarm_count",
    "recurring_rate",
    "avg_ack_delay",
    "critical_count",
    "active_count",
    "suppression_candidate_rate",
]
SUPPORTED_GROUP_BY = [
    "alarm_name",
    "alarm_code",
    "asset_id",
    "asset_name",
    "severity",
    "alarm_type",
    "unit",
    "site",
    "status",
]


def alarm_summary(alarms, group_by, kpis):
    groups = defaultdict(list)
    for alarm in alarms:
        key = tuple(alarm[field] for field in group_by)
        groups[key].append(alarm)

    rows = []
    for key, items in groups.items():
        row = dict(zip(group_by, key, strict=True))
        row.update(compute_kpis(items, kpis))
        row["_count"] = len(items)
        rows.append(row)

    rows.sort(key=lambda r: -r.pop("_count"))
    return {
        "total_alarms": len(alarms),
        "overall": compute_kpis(alarms, kpis),
        "groups": rows,
    }


def alarm_trends(alarms, start_time, end_time, bucket, metrics):
    step = {"hourly": timedelta(hours=1), "daily": timedelta(days=1), "weekly": timedelta(days=7)}[bucket]

    # Align the first bucket to midnight (or to the hour)
    if bucket == "hourly":
        first = start_time.replace(minute=0, second=0, microsecond=0)
    else:
        first = start_time.replace(hour=0, minute=0, second=0, microsecond=0)

    buckets = defaultdict(list)
    for alarm in alarms:
        index = int((parse_time(alarm["start_time"]) - first) / step)
        buckets[index].append(alarm)

    series = []
    current = first
    index = 0
    while current < end_time:
        row = {"bucket_start": to_iso(current)}
        row.update(compute_kpis(buckets.get(index, []), metrics))
        series.append(row)
        current += step
        index += 1

    counts = [row.get("alarm_count", 0) for row in series]
    direction = "flat"
    if len(counts) >= 4:
        half = len(counts) // 2
        first_half = sum(counts[:half]) / half
        second_half = sum(counts[half:]) / (len(counts) - half)
        if second_half > first_half * 1.15:
            direction = "increasing"
        elif second_half < first_half * 0.85:
            direction = "decreasing"

    return {"bucket": bucket, "series": series, "trend_direction": direction}


# =========================
# Correlation
# =========================


def correlate(alarms, asset_ids, lag_window_minutes, severity_threshold, min_support):
    """
    Co-occurrence correlation.

    For every alarm A we look at alarms B that started within `lag_window_minutes`
    AFTER A. Each (A, B) pair is counted. Pairs seen at least `min_support`
    times are reported. We include the related assets of the requested assets,
    because the cause of an alarm is often on a neighbouring asset.
    """
    scope = set(asset_ids)
    for asset_id in asset_ids:
        for rel in ASSETS_BY_ID[asset_id]["related_assets"]:
            scope.add(rel["asset_id"])

    min_level = SEVERITY_ORDER[severity_threshold]
    events = [a for a in alarms if a["asset_id"] in scope and SEVERITY_ORDER[a["severity"]] >= min_level]
    events.sort(key=lambda x: x["start_time"])
    times = [parse_time(e["start_time"]) for e in events]

    window = timedelta(minutes=lag_window_minutes)
    pair_count = Counter()
    pair_lags = defaultdict(list)
    leading_count = Counter()

    for i, first in enumerate(events):
        key_a = (first["asset_id"], first["alarm_name"])
        leading_count[key_a] += 1
        j = i + 1
        seen_after_a = set()  # count each following alarm type once per A, so confidence stays <= 100%
        while j < len(events) and times[j] - times[i] <= window:
            second = events[j]
            key_b = (second["asset_id"], second["alarm_name"])
            if key_b != key_a and key_b not in seen_after_a:
                seen_after_a.add(key_b)
                pair_count[(key_a, key_b)] += 1
                pair_lags[(key_a, key_b)].append((times[j] - times[i]).total_seconds() / 60)
            j += 1

    pairs = []
    for (key_a, key_b), support in pair_count.items():
        if support < min_support:
            continue
        lags = pair_lags[(key_a, key_b)]
        pairs.append(
            {
                "leading_alarm": {
                    "asset_id": key_a[0],
                    "asset_name": ASSETS_BY_ID[key_a[0]]["asset_name"],
                    "alarm_name": key_a[1],
                },
                "following_alarm": {
                    "asset_id": key_b[0],
                    "asset_name": ASSETS_BY_ID[key_b[0]]["asset_name"],
                    "alarm_name": key_b[1],
                },
                "support": support,
                "confidence": round(support / leading_count[key_a], 3),
                "avg_lag_minutes": round(sum(lags) / len(lags), 1),
            }
        )

    pairs.sort(key=lambda p: (-p["support"], -p["confidence"]))
    return {
        "assets_in_scope": sorted(scope),
        "events_analyzed": len(events),
        "correlated_pairs": pairs[:20],
    }


# =========================
# Flood analysis
# =========================


def flood_analysis(alarms, threshold_count, rolling_window_minutes, start_time, end_time):
    """A 'flood' is when >= threshold_count alarms start inside a rolling window."""
    events = sorted(alarms, key=lambda x: x["start_time"])
    times = [parse_time(e["start_time"]) for e in events]
    window = timedelta(minutes=rolling_window_minutes)

    windows = []
    left = 0
    for right in range(len(events)):
        while times[right] - times[left] > window:
            left += 1
        if right - left + 1 >= threshold_count:
            start, end = times[left], times[right]
            if windows and start <= windows[-1]["_end"]:
                windows[-1]["_end"] = max(end, windows[-1]["_end"])
                windows[-1]["_items"].update(range(left, right + 1))
            else:
                windows.append({"_start": start, "_end": end, "_items": set(range(left, right + 1))})

    flood_windows = []
    seconds_in_flood = 0
    for w in windows:
        items = [events[i] for i in sorted(w["_items"])]
        top = Counter(f"{a['asset_name']} - {a['alarm_name']}" for a in items).most_common(3)
        seconds_in_flood += max(60, (w["_end"] - w["_start"]).total_seconds())
        flood_windows.append(
            {
                "start": to_iso(w["_start"]),
                "end": to_iso(w["_end"] + timedelta(minutes=1)),
                "alarm_count": len(items),
                "assets": sorted({a["asset_name"] for a in items}),
                "top_alarms": [{"alarm": name, "count": c} for name, c in top],
            }
        )

    total_seconds = max(1, (end_time - start_time).total_seconds())
    return {
        "total_alarms": len(events),
        "flood_count": len(flood_windows),
        "percent_time_in_flood": round(100 * seconds_in_flood / total_seconds, 3),
        "flood_windows": flood_windows,
    }


# =========================
# Rationalization candidates
# =========================


def rationalization_candidates(alarms, recurrence_threshold, stale_minutes_threshold, now):
    groups = defaultdict(list)
    for alarm in alarms:
        groups[(alarm["asset_id"], alarm["alarm_name"])].append(alarm)

    candidates = []
    for (asset_id, alarm_name), items in groups.items():
        reasons = []
        count = len(items)
        fleeting = sum(1 for a in items if a["duration_seconds"] is not None and a["duration_seconds"] < 60)
        stale = 0
        for a in items:
            if a["status"] in ("active", "acknowledged"):
                age_min = (now - parse_time(a["start_time"])).total_seconds() / 60
                if age_min > stale_minutes_threshold:
                    stale += 1
            elif a["duration_seconds"] and a["duration_seconds"] / 60 > stale_minutes_threshold:
                stale += 1

        if count >= recurrence_threshold:
            reasons.append(f"recurring: fired {count} times (threshold {recurrence_threshold})")
        if count and fleeting / count >= 0.25:
            reasons.append(f"chattering: {fleeting} of {count} cleared in under 60 seconds")
        if stale:
            reasons.append(f"stale: {stale} occurrence(s) stayed open longer than {stale_minutes_threshold} min")
        if not reasons:
            continue

        score = min(100, count * 2 + fleeting * 3 + stale * 10)
        candidates.append(
            {
                "asset_id": asset_id,
                "asset_name": ASSETS_BY_ID[asset_id]["asset_name"],
                "alarm_name": alarm_name,
                "alarm_code": items[0]["alarm_code"],
                "occurrences": count,
                "fleeting_count": fleeting,
                "stale_count": stale,
                "reasons": reasons,
                "rationalization_score": score,
            }
        )

    candidates.sort(key=lambda c: -c["rationalization_score"])
    return candidates


# =========================
# Priority score
# =========================

CRITICALITY_POINTS = {"low": 5, "medium": 12, "high": 20}
SEVERITY_POINTS = {"low": 10, "medium": 20, "high": 30, "critical": 40}


def priority_score(alarm, all_alarms):
    asset = ASSETS_BY_ID[alarm["asset_id"]]
    start = parse_time(alarm["start_time"])
    last_30_days = [
        a
        for a in all_alarms
        if a["asset_id"] == alarm["asset_id"]
        and a["alarm_name"] == alarm["alarm_name"]
        and timedelta(0) <= start - parse_time(a["start_time"]) <= timedelta(days=30)
    ]

    factors = [
        {"factor": "severity", "value": alarm["severity"], "points": SEVERITY_POINTS[alarm["severity"]]},
        {
            "factor": "asset_criticality",
            "value": asset["criticality"],
            "points": CRITICALITY_POINTS[asset["criticality"]],
        },
        {"factor": "recurrence_30d", "value": len(last_30_days), "points": min(20, len(last_30_days))},
        {"factor": "status", "value": alarm["status"], "points": 10 if alarm["status"] == "active" else 0},
        {"factor": "alarm_type", "value": alarm["alarm_type"], "points": 10 if alarm["alarm_type"] == "safety" else 0},
    ]
    score = min(100, sum(f["points"] for f in factors))
    if score >= 75:
        level = "P1"
    elif score >= 55:
        level = "P2"
    elif score >= 35:
        level = "P3"
    else:
        level = "P4"

    top = sorted(factors, key=lambda f: -f["points"])[:2]
    explanation = (
        f"{alarm['alarm_name']} on {asset['asset_name']} scored {score}/100 ({level}). "
        f"Main drivers: {top[0]['factor']}={top[0]['value']}, {top[1]['factor']}={top[1]['value']}."
    )
    return {
        "alarm_id": alarm["alarm_id"],
        "priority_score": score,
        "priority_level": level,
        "factors": factors,
        "explanation": explanation,
    }


# =========================
# Operator recommendations
# =========================
# NOTE: One recommendation (pump restart) intentionally disagrees with the
# operating procedure in the document corpus, so the copilot can show how it
# detects conflicting evidence.

RECOMMENDATION_RULES = {
    "High Discharge Pressure": [
        ("Check the position of the downstream control valve and confirm it is not closing unexpectedly", "immediate"),
        ("Verify discharge pressure on the local gauge to rule out a faulty transmitter", "immediate"),
        ("Reduce load or open the recirculation (minimum flow) line to bring pressure below the limit", "immediate"),
        ("If pressure stays high, reset the trip and restart the pump to clear the alarm", "short_term"),
    ],
    "High Bearing Temperature": [
        ("Check lube oil level and oil temperature at the bearing housing", "immediate"),
        ("Check vibration readings for signs of bearing damage", "immediate"),
        ("Plan a bearing inspection if temperature keeps rising", "short_term"),
    ],
    "High Vibration": [
        ("Compare vibration with the last baseline reading", "immediate"),
        ("Check for loose foundation bolts and coupling misalignment", "short_term"),
    ],
    "Low Suction Pressure": [
        ("Check the suction source level (deaerator or tank level)", "immediate"),
        ("Check the suction strainer for blockage", "short_term"),
    ],
    "Seal Leak Detected": [
        ("Isolate the area and check for leakage visually using proper PPE", "immediate"),
        ("Plan a mechanical seal replacement", "short_term"),
    ],
    "Motor Trip": [
        ("Check the protection relay to identify which protection operated", "immediate"),
        ("Check lube oil pressure history just before the trip", "immediate"),
        ("Measure insulation resistance before any restart attempt", "short_term"),
    ],
    "High Winding Temperature": [
        ("Check motor current and cooling fan operation", "immediate"),
        ("Clean the motor cooling air path if blocked", "short_term"),
    ],
    "Overcurrent": [
        ("Check the driven equipment for mechanical overload", "immediate"),
        ("Check supply voltage balance", "short_term"),
    ],
    "High Discharge Temperature": [
        ("Check discharge cooler outlet temperature and cooling water flow", "immediate"),
        ("Check suction temperature and compression ratio", "short_term"),
    ],
    "Surge Detected": [
        ("Open the anti-surge valve and confirm the controller is in automatic", "immediate"),
        ("Check the operating point against the surge line", "short_term"),
    ],
    "Low Lube Oil Pressure": [
        ("Start the standby lube oil pump", "immediate"),
        ("Check the lube oil filter differential pressure and oil level", "immediate"),
    ],
    "Valve Position Deviation": [
        ("Compare valve demand and feedback signal", "immediate"),
        ("Check instrument air supply to the valve positioner", "short_term"),
    ],
    "High Outlet Temperature": [
        ("Check cooling water supply temperature and flow to the cooler", "immediate"),
        ("Plan cleaning of the cooler if fouling is suspected", "short_term"),
    ],
}

# Some alarms need different advice depending on the equipment type
RECOMMENDATION_OVERRIDES = {
    ("compressor", "High Discharge Pressure"): [
        ("Check discharge cooler outlet temperature and cooling water flow", "immediate"),
        ("Confirm the recycle (anti-surge) valve controller is in automatic", "immediate"),
        ("Check that the downstream block valve is fully open", "short_term"),
    ],
}

DEFAULT_RECOMMENDATIONS = [
    ("Confirm the alarm locally and check the process value trend", "immediate"),
    ("Follow the site operating procedure for this equipment", "short_term"),
]


def operator_recommendations(
    alarm, all_alarms, include_related=True, include_asset_context=True, include_historical_pattern=True
):
    asset_type = ASSETS_BY_ID[alarm["asset_id"]]["asset_type"]
    rules = RECOMMENDATION_OVERRIDES.get((asset_type, alarm["alarm_name"])) or RECOMMENDATION_RULES.get(
        alarm["alarm_name"], DEFAULT_RECOMMENDATIONS
    )
    actions = [
        {"step": i + 1, "action": text, "urgency": urgency, "source": "alarm_api_rule_engine"}
        for i, (text, urgency) in enumerate(rules)
    ]
    response = {
        "alarm_id": alarm["alarm_id"],
        "alarm_name": alarm["alarm_name"],
        "asset_id": alarm["asset_id"],
        "asset_name": alarm["asset_name"],
        "severity": alarm["severity"],
        "recommended_actions": actions,
    }

    asset = ASSETS_BY_ID[alarm["asset_id"]]
    if include_related:
        response["related_assets_to_check"] = [
            {
                "asset_id": rel["asset_id"],
                "asset_name": ASSETS_BY_ID[rel["asset_id"]]["asset_name"],
                "relationship": rel["relationship"],
            }
            for rel in asset["related_assets"]
        ]
    if include_asset_context:
        response["asset_context"] = {
            "asset_type": asset["asset_type"],
            "criticality": asset["criticality"],
            "last_maintenance_date": asset["last_maintenance_date"],
            "operating_limits": asset["operating_limits"],
        }
    if include_historical_pattern:
        same = [a for a in all_alarms if a["asset_id"] == alarm["asset_id"] and a["alarm_name"] == alarm["alarm_name"]]
        by_hour = Counter(parse_time(a["start_time"]).hour for a in same)
        response["historical_pattern"] = {
            "occurrences_total": len(same),
            "most_common_hours_utc": [h for h, _ in by_hour.most_common(3)],
            "first_seen": same[0]["start_time"] if same else None,
            "last_seen": same[-1]["start_time"] if same else None,
        }
    return response


# =========================
# KPI calculation (generate + execute)
# =========================

KPI_DEFINITIONS = [
    {
        "calculation_type": "alarm_flood_index",
        "description": "Percentage of time the scope was in an alarm flood (>=10 alarms in 10 minutes)",
        "unit": "%",
    },
    {
        "calculation_type": "critical_alarm_density",
        "description": "Critical alarms per asset per day",
        "unit": "alarms/asset/day",
    },
    {
        "calculation_type": "operator_response_efficiency",
        "description": "Share of alarms acknowledged within 10 minutes",
        "unit": "%",
    },
    {
        "calculation_type": "nuisance_alarm_score",
        "description": "0-100 score based on fleeting (<60 s) and recurring alarms",
        "unit": "score",
    },
    {"calculation_type": "avg_ack_delay", "description": "Average acknowledgement delay", "unit": "seconds"},
]

CALCULATIONS = {}  # in-memory store: calculation_id -> definition


def generate_calculation(calculation_type, filters):
    calc_id = f"CALC-{uuid.uuid4().hex[:8]}"
    code = f"alarms = get_alarms(filters={filters!r})\nresult = {calculation_type}(alarms)"
    CALCULATIONS[calc_id] = {"calculation_type": calculation_type, "filters": filters, "code": code}
    return {
        "calculation_id": calc_id,
        "calculation_type": calculation_type,
        "generated_code": code,
        "filters": filters,
        "status": "generated",
    }


def execute_calculation(calc_id, alarms, start_time, end_time):
    definition = CALCULATIONS[calc_id]
    calc_type = definition["calculation_type"]
    days = max(1.0, (end_time - start_time).total_seconds() / 86400)
    count = len(alarms)

    if calc_type == "alarm_flood_index":
        flood = flood_analysis(alarms, 10, 10, start_time, end_time)
        value, details = flood["percent_time_in_flood"], {"flood_count": flood["flood_count"]}
    elif calc_type == "critical_alarm_density":
        assets = {a["asset_id"] for a in alarms} or {"none"}
        critical = sum(1 for a in alarms if a["severity"] == "critical")
        value = round(critical / len(assets) / days, 4)
        details = {"critical_alarms": critical, "assets": len(assets), "days": round(days, 1)}
    elif calc_type == "operator_response_efficiency":
        acked = [a for a in alarms if a["ack_delay_seconds"] is not None]
        fast = sum(1 for a in acked if a["ack_delay_seconds"] <= 600)
        value = round(100 * fast / len(acked), 2) if acked else 0.0
        details = {"acknowledged": len(acked), "within_10_min": fast}
    elif calc_type == "nuisance_alarm_score":
        kpis = compute_kpis(alarms, ["suppression_candidate_rate", "recurring_rate"])
        value = round(100 * (0.6 * kpis["suppression_candidate_rate"] + 0.4 * kpis["recurring_rate"]), 1)
        details = kpis
    else:  # avg_ack_delay
        value = compute_kpis(alarms, ["avg_ack_delay"])["avg_ack_delay"]
        details = {}

    unit = next(d["unit"] for d in KPI_DEFINITIONS if d["calculation_type"] == calc_type)
    return {
        "calculation_id": calc_id,
        "calculation_type": calc_type,
        "result": {"value": value, "unit": unit, "alarms_considered": count, "details": details},
        "executed_at": to_iso(datetime.now(timezone.utc)),
    }
