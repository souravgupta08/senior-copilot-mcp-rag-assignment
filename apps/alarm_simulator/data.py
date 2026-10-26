"""
Fake (synthetic) plant data for the Alarm Management API simulator.

We create:
- a list of ASSETS (pumps, motors, compressors, valves ...)
- a list of ALARMS raised on those assets

Everything is generated with a fixed random seed, so the data looks the
same every time the simulator starts. That makes tests repeatable.
"""

import random
from datetime import datetime, timedelta, timezone

# =========================
# Assets
# =========================

ASSETS = [
    # ---- NorthPlant / Unit 1 : boiler feed water system ----
    {
        "asset_id": "AST-BFP-101",
        "asset_name": "Boiler Feed Pump 101",
        "asset_type": "pump",
        "site": "NorthPlant",
        "unit": "Unit 1",
        "criticality": "high",
        "manufacturer": "Flowserve",
        "model": "HDX-250",
        "install_date": "2015-03-12",
        "last_maintenance_date": "2026-02-18",
        "operating_limits": {"discharge_pressure_bar": 120, "bearing_temp_c": 85, "vibration_mm_s": 7.1},
        "related_assets": [
            {"asset_id": "AST-MTR-101", "relationship": "driven_by"},
            {"asset_id": "AST-FCV-101", "relationship": "downstream_valve"},
            {"asset_id": "AST-DEA-101", "relationship": "suction_source"},
        ],
    },
    {
        "asset_id": "AST-BFP-102",
        "asset_name": "Boiler Feed Pump 102",
        "asset_type": "pump",
        "site": "NorthPlant",
        "unit": "Unit 1",
        "criticality": "high",
        "manufacturer": "Flowserve",
        "model": "HDX-250",
        "install_date": "2016-07-01",
        "last_maintenance_date": "2025-11-04",
        "operating_limits": {"discharge_pressure_bar": 120, "bearing_temp_c": 85, "vibration_mm_s": 7.1},
        "related_assets": [
            {"asset_id": "AST-MTR-102", "relationship": "driven_by"},
            {"asset_id": "AST-FCV-101", "relationship": "downstream_valve"},
            {"asset_id": "AST-DEA-101", "relationship": "suction_source"},
        ],
    },
    {
        "asset_id": "AST-MTR-101",
        "asset_name": "BFP Motor 101",
        "asset_type": "motor",
        "site": "NorthPlant",
        "unit": "Unit 1",
        "criticality": "high",
        "manufacturer": "ABB",
        "model": "AMA-500",
        "install_date": "2015-03-12",
        "last_maintenance_date": "2026-01-10",
        "operating_limits": {"winding_temp_c": 130, "current_a": 410},
        "related_assets": [{"asset_id": "AST-BFP-101", "relationship": "drives"}],
    },
    {
        "asset_id": "AST-MTR-102",
        "asset_name": "BFP Motor 102",
        "asset_type": "motor",
        "site": "NorthPlant",
        "unit": "Unit 1",
        "criticality": "high",
        "manufacturer": "ABB",
        "model": "AMA-500",
        "install_date": "2016-07-01",
        "last_maintenance_date": "2025-09-22",
        "operating_limits": {"winding_temp_c": 130, "current_a": 410},
        "related_assets": [{"asset_id": "AST-BFP-102", "relationship": "drives"}],
    },
    {
        "asset_id": "AST-FCV-101",
        "asset_name": "Feedwater Control Valve FCV-101",
        "asset_type": "valve",
        "site": "NorthPlant",
        "unit": "Unit 1",
        "criticality": "medium",
        "manufacturer": "Fisher",
        "model": "EWT-8",
        "install_date": "2015-03-12",
        "last_maintenance_date": "2025-06-30",
        "operating_limits": {"position_deviation_pct": 5},
        "related_assets": [
            {"asset_id": "AST-BFP-101", "relationship": "upstream_pump"},
            {"asset_id": "AST-BFP-102", "relationship": "upstream_pump"},
        ],
    },
    {
        "asset_id": "AST-DEA-101",
        "asset_name": "Deaerator Tank D-101",
        "asset_type": "vessel",
        "site": "NorthPlant",
        "unit": "Unit 1",
        "criticality": "medium",
        "manufacturer": "Stork",
        "model": "DT-40",
        "install_date": "2014-11-20",
        "last_maintenance_date": "2025-12-01",
        "operating_limits": {"level_pct_low": 30, "level_pct_high": 85},
        "related_assets": [
            {"asset_id": "AST-BFP-101", "relationship": "feeds"},
            {"asset_id": "AST-BFP-102", "relationship": "feeds"},
        ],
    },
    # ---- NorthPlant / Unit 2 : boiler ----
    {
        "asset_id": "AST-BLR-201",
        "asset_name": "Boiler B-201",
        "asset_type": "boiler",
        "site": "NorthPlant",
        "unit": "Unit 2",
        "criticality": "high",
        "manufacturer": "Babcock",
        "model": "SB-90",
        "install_date": "2012-05-05",
        "last_maintenance_date": "2026-03-15",
        "operating_limits": {"flue_gas_temp_c": 220},
        "related_assets": [{"asset_id": "AST-SDR-201", "relationship": "part_of"}],
    },
    {
        "asset_id": "AST-SDR-201",
        "asset_name": "Steam Drum SD-201",
        "asset_type": "drum",
        "site": "NorthPlant",
        "unit": "Unit 2",
        "criticality": "high",
        "manufacturer": "Babcock",
        "model": "SD-90",
        "install_date": "2012-05-05",
        "last_maintenance_date": "2026-03-15",
        "operating_limits": {"level_mm_low": -150},
        "related_assets": [{"asset_id": "AST-BLR-201", "relationship": "part_of"}],
    },
    # ---- SouthPlant / Unit 3 + Unit 4 : utilities ----
    {
        "asset_id": "AST-CWP-301",
        "asset_name": "Cooling Water Pump 301",
        "asset_type": "pump",
        "site": "SouthPlant",
        "unit": "Unit 3",
        "criticality": "medium",
        "manufacturer": "KSB",
        "model": "Omega-200",
        "install_date": "2018-02-14",
        "last_maintenance_date": "2026-04-02",
        "operating_limits": {"discharge_pressure_bar": 6, "bearing_temp_c": 80, "vibration_mm_s": 7.1},
        "related_assets": [{"asset_id": "AST-CTW-301", "relationship": "supplies"}],
    },
    {
        "asset_id": "AST-CTW-301",
        "asset_name": "Cooling Tower CT-301",
        "asset_type": "cooling_tower",
        "site": "SouthPlant",
        "unit": "Unit 3",
        "criticality": "medium",
        "manufacturer": "SPX",
        "model": "Marley-NC",
        "install_date": "2018-02-14",
        "last_maintenance_date": "2026-01-20",
        "operating_limits": {"basin_temp_c": 32},
        "related_assets": [{"asset_id": "AST-CWP-301", "relationship": "supplied_by"}],
    },
    {
        "asset_id": "AST-ACP-401",
        "asset_name": "Air Compressor AC-401",
        "asset_type": "compressor",
        "site": "SouthPlant",
        "unit": "Unit 4",
        "criticality": "medium",
        "manufacturer": "Atlas Copco",
        "model": "GA-90",
        "install_date": "2019-09-09",
        "last_maintenance_date": "2026-05-11",
        "operating_limits": {"discharge_pressure_bar": 10, "discharge_temp_c": 110},
        "related_assets": [{"asset_id": "AST-ADR-401", "relationship": "downstream_dryer"}],
    },
    {
        "asset_id": "AST-ADR-401",
        "asset_name": "Air Dryer AD-401",
        "asset_type": "dryer",
        "site": "SouthPlant",
        "unit": "Unit 4",
        "criticality": "low",
        "manufacturer": "Atlas Copco",
        "model": "FD-120",
        "install_date": "2019-09-09",
        "last_maintenance_date": "2026-05-11",
        "operating_limits": {"dew_point_c": 3},
        "related_assets": [{"asset_id": "AST-ACP-401", "relationship": "upstream_compressor"}],
    },
    # ---- EastRefinery / Unit 5 : gas compression ----
    {
        "asset_id": "AST-GCK-501",
        "asset_name": "Gas Compressor K-501",
        "asset_type": "compressor",
        "site": "EastRefinery",
        "unit": "Unit 5",
        "criticality": "high",
        "manufacturer": "Siemens",
        "model": "STC-SV",
        "install_date": "2017-04-18",
        "last_maintenance_date": "2026-02-02",
        "operating_limits": {"discharge_pressure_bar": 45, "discharge_temp_c": 150},
        "related_assets": [
            {"asset_id": "AST-MTR-501", "relationship": "driven_by"},
            {"asset_id": "AST-EXC-501", "relationship": "discharge_cooler"},
            {"asset_id": "AST-LOP-501", "relationship": "lube_oil_supply"},
        ],
    },
    {
        "asset_id": "AST-GCK-502",
        "asset_name": "Gas Compressor K-502",
        "asset_type": "compressor",
        "site": "EastRefinery",
        "unit": "Unit 5",
        "criticality": "high",
        "manufacturer": "Siemens",
        "model": "STC-SV",
        "install_date": "2017-04-18",
        "last_maintenance_date": "2026-06-20",
        "operating_limits": {"discharge_pressure_bar": 45, "discharge_temp_c": 150},
        "related_assets": [
            {"asset_id": "AST-MTR-502", "relationship": "driven_by"},
            {"asset_id": "AST-EXC-501", "relationship": "discharge_cooler"},
        ],
    },
    {
        "asset_id": "AST-MTR-501",
        "asset_name": "Compressor Motor M-501",
        "asset_type": "motor",
        "site": "EastRefinery",
        "unit": "Unit 5",
        "criticality": "high",
        "manufacturer": "WEG",
        "model": "W22-1000",
        "install_date": "2017-04-18",
        "last_maintenance_date": "2025-12-12",
        "operating_limits": {"winding_temp_c": 135, "current_a": 980},
        "related_assets": [
            {"asset_id": "AST-GCK-501", "relationship": "drives"},
            {"asset_id": "AST-LOP-501", "relationship": "shares_lube_system"},
        ],
    },
    {
        "asset_id": "AST-MTR-502",
        "asset_name": "Compressor Motor M-502",
        "asset_type": "motor",
        "site": "EastRefinery",
        "unit": "Unit 5",
        "criticality": "high",
        "manufacturer": "WEG",
        "model": "W22-1000",
        "install_date": "2017-04-18",
        "last_maintenance_date": "2026-06-20",
        "operating_limits": {"winding_temp_c": 135, "current_a": 980},
        "related_assets": [{"asset_id": "AST-GCK-502", "relationship": "drives"}],
    },
    {
        "asset_id": "AST-LOP-501",
        "asset_name": "Lube Oil Pump LOP-501",
        "asset_type": "lube_pump",
        "site": "EastRefinery",
        "unit": "Unit 5",
        "criticality": "high",
        "manufacturer": "Viking",
        "model": "LS-32",
        "install_date": "2017-04-18",
        "last_maintenance_date": "2025-10-30",
        "operating_limits": {"lube_oil_pressure_bar_low": 1.5},
        "related_assets": [
            {"asset_id": "AST-GCK-501", "relationship": "supplies"},
            {"asset_id": "AST-MTR-501", "relationship": "supplies"},
        ],
    },
    {
        "asset_id": "AST-EXC-501",
        "asset_name": "Discharge Cooler E-501",
        "asset_type": "heat_exchanger",
        "site": "EastRefinery",
        "unit": "Unit 5",
        "criticality": "medium",
        "manufacturer": "Alfa Laval",
        "model": "T20",
        "install_date": "2017-04-18",
        "last_maintenance_date": "2025-08-08",
        "operating_limits": {"outlet_temp_c": 55},
        "related_assets": [
            {"asset_id": "AST-GCK-501", "relationship": "cools"},
            {"asset_id": "AST-GCK-502", "relationship": "cools"},
        ],
    },
]

ASSETS_BY_ID = {asset["asset_id"]: asset for asset in ASSETS}


# =========================
# Alarm templates per asset type
# =========================
# rate = how many times per day (on average) this alarm fires
# severities = which severities this alarm can have

ALARM_TEMPLATES = {
    "pump": [
        {
            "alarm_name": "High Discharge Pressure",
            "alarm_code": "PMP-PH-01",
            "alarm_type": "process",
            "rate": 0.25,
            "severities": ["medium", "high", "critical"],
            "measure": "bar",
        },
        {
            "alarm_name": "Low Suction Pressure",
            "alarm_code": "PMP-PL-02",
            "alarm_type": "process",
            "rate": 0.12,
            "severities": ["medium", "high"],
            "measure": "bar",
        },
        {
            "alarm_name": "High Bearing Temperature",
            "alarm_code": "PMP-TH-03",
            "alarm_type": "device",
            "rate": 0.10,
            "severities": ["medium", "high", "critical"],
            "measure": "degC",
        },
        {
            "alarm_name": "High Vibration",
            "alarm_code": "PMP-VH-04",
            "alarm_type": "device",
            "rate": 0.10,
            "severities": ["low", "medium", "high"],
            "measure": "mm/s",
        },
        {
            "alarm_name": "Seal Leak Detected",
            "alarm_code": "PMP-SL-05",
            "alarm_type": "safety",
            "rate": 0.03,
            "severities": ["high"],
            "measure": "status",
        },
    ],
    "motor": [
        {
            "alarm_name": "Motor Trip",
            "alarm_code": "MTR-TR-01",
            "alarm_type": "safety",
            "rate": 0.05,
            "severities": ["high", "critical"],
            "measure": "status",
        },
        {
            "alarm_name": "High Winding Temperature",
            "alarm_code": "MTR-TH-02",
            "alarm_type": "device",
            "rate": 0.10,
            "severities": ["medium", "high"],
            "measure": "degC",
        },
        {
            "alarm_name": "Overcurrent",
            "alarm_code": "MTR-OC-03",
            "alarm_type": "device",
            "rate": 0.08,
            "severities": ["medium", "high"],
            "measure": "A",
        },
        {
            "alarm_name": "High Vibration",
            "alarm_code": "MTR-VH-04",
            "alarm_type": "device",
            "rate": 0.06,
            "severities": ["low", "medium"],
            "measure": "mm/s",
        },
    ],
    "compressor": [
        {
            "alarm_name": "High Discharge Pressure",
            "alarm_code": "CMP-PH-01",
            "alarm_type": "process",
            "rate": 0.25,
            "severities": ["medium", "high", "critical"],
            "measure": "bar",
        },
        {
            "alarm_name": "High Discharge Temperature",
            "alarm_code": "CMP-TH-02",
            "alarm_type": "process",
            "rate": 0.12,
            "severities": ["medium", "high"],
            "measure": "degC",
        },
        {
            "alarm_name": "Surge Detected",
            "alarm_code": "CMP-SG-03",
            "alarm_type": "safety",
            "rate": 0.04,
            "severities": ["high", "critical"],
            "measure": "status",
        },
        {
            "alarm_name": "Low Lube Oil Pressure",
            "alarm_code": "CMP-LO-04",
            "alarm_type": "device",
            "rate": 0.05,
            "severities": ["high"],
            "measure": "bar",
        },
    ],
    "valve": [
        {
            "alarm_name": "Valve Position Deviation",
            "alarm_code": "VLV-PD-01",
            "alarm_type": "device",
            "rate": 0.20,
            "severities": ["low", "medium"],
            "measure": "%",
        },
        {
            "alarm_name": "Valve Stuck",
            "alarm_code": "VLV-ST-02",
            "alarm_type": "device",
            "rate": 0.03,
            "severities": ["high"],
            "measure": "status",
        },
    ],
    "vessel": [
        {
            "alarm_name": "Low Level",
            "alarm_code": "VSL-LL-01",
            "alarm_type": "process",
            "rate": 0.08,
            "severities": ["medium", "high"],
            "measure": "%",
        },
        {
            "alarm_name": "High Level",
            "alarm_code": "VSL-LH-02",
            "alarm_type": "process",
            "rate": 0.05,
            "severities": ["medium"],
            "measure": "%",
        },
    ],
    "boiler": [
        {
            "alarm_name": "High Flue Gas Temperature",
            "alarm_code": "BLR-FG-01",
            "alarm_type": "process",
            "rate": 0.15,
            "severities": ["low", "medium", "high"],
            "measure": "degC",
        },
        {
            "alarm_name": "Flame Failure",
            "alarm_code": "BLR-FF-02",
            "alarm_type": "safety",
            "rate": 0.02,
            "severities": ["critical"],
            "measure": "status",
        },
    ],
    "drum": [
        {
            "alarm_name": "Low Drum Level",
            "alarm_code": "DRM-LL-01",
            "alarm_type": "safety",
            "rate": 0.10,
            "severities": ["medium", "high", "critical"],
            "measure": "mm",
        },
    ],
    "cooling_tower": [
        {
            "alarm_name": "High Basin Temperature",
            "alarm_code": "CTW-TH-01",
            "alarm_type": "process",
            "rate": 0.15,
            "severities": ["low", "medium"],
            "measure": "degC",
        },
        {
            "alarm_name": "Fan Vibration High",
            "alarm_code": "CTW-VH-02",
            "alarm_type": "device",
            "rate": 0.05,
            "severities": ["medium"],
            "measure": "mm/s",
        },
    ],
    "dryer": [
        {
            "alarm_name": "High Dew Point",
            "alarm_code": "DRY-DP-01",
            "alarm_type": "process",
            "rate": 0.30,
            "severities": ["low"],
            "measure": "degC",
        },
    ],
    "lube_pump": [
        {
            "alarm_name": "Low Lube Oil Pressure",
            "alarm_code": "LOP-PL-01",
            "alarm_type": "device",
            "rate": 0.10,
            "severities": ["medium", "high"],
            "measure": "bar",
        },
    ],
    "heat_exchanger": [
        {
            "alarm_name": "High Outlet Temperature",
            "alarm_code": "EXC-TH-01",
            "alarm_type": "process",
            "rate": 0.15,
            "severities": ["medium", "high"],
            "measure": "degC",
        },
    ],
}

SEVERITY_ORDER = {"low": 1, "medium": 2, "high": 3, "critical": 4}

DATA_START = datetime(2026, 4, 1, tzinfo=timezone.utc)


# =========================
# Small helpers
# =========================


def to_iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(value: str) -> datetime:
    """Accepts '2026-05-01T00:00:00Z' or '2026-05-01' style strings."""
    value = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def find_template(asset_type: str, alarm_name: str) -> dict:
    for template in ALARM_TEMPLATES[asset_type]:
        if template["alarm_name"] == alarm_name:
            return template
    raise KeyError(f"No template {alarm_name} for {asset_type}")


# =========================
# Alarm generator
# =========================


class AlarmFactory:
    """Builds alarm dictionaries and gives each one a unique id."""

    def __init__(self, rng: random.Random, now: datetime):
        self.rng = rng
        self.now = now
        self.counter = 0
        self.alarms = []

    def make(
        self,
        asset: dict,
        alarm_name: str,
        start: datetime,
        severity: str = None,
        duration_s: int = None,
        active: bool = False,
    ):
        if start > self.now:
            return None

        template = find_template(asset["asset_type"], alarm_name)
        rng = self.rng

        if severity is None:
            severity = rng.choice(template["severities"])

        if duration_s is None:
            # Most alarms clear in 5-90 minutes. Some are "fleeting" (< 60 s).
            if rng.random() < 0.15:
                duration_s = rng.randint(5, 55)
            else:
                duration_s = rng.randint(5 * 60, 90 * 60)

        ack_delay_s = rng.randint(30, 20 * 60)
        if severity in ("low", "medium") and rng.random() < 0.2:
            ack_delay_s = rng.randint(20 * 60, 4 * 3600)  # slow acks on low priority alarms

        end_time = start + timedelta(seconds=duration_s)
        ack_time = start + timedelta(seconds=ack_delay_s)

        # Decide status based on time
        if active or end_time > self.now:
            status = "acknowledged" if ack_time <= self.now and not active else "active"
            end_time = None
            if status == "active":
                ack_time = None
        else:
            status = "cleared"

        self.counter += 1
        alarm = {
            "alarm_id": f"ALM-{self.counter:06d}",
            "asset_id": asset["asset_id"],
            "asset_name": asset["asset_name"],
            "site": asset["site"],
            "unit": asset["unit"],
            "alarm_name": alarm_name,
            "alarm_code": template["alarm_code"],
            "alarm_type": template["alarm_type"],
            "severity": severity,
            "status": status,
            "start_time": to_iso(start),
            "end_time": to_iso(end_time) if end_time else None,
            "ack_time": to_iso(ack_time) if ack_time else None,
            "ack_delay_seconds": ack_delay_s if ack_time else None,
            "duration_seconds": duration_s if end_time else None,
            "measure_unit": template["measure"],
            "description": f"{alarm_name} on {asset['asset_name']}",
        }
        self.alarms.append(alarm)
        return alarm


def build_alarms(now: datetime = None, seed: int = 42) -> list[dict]:
    """
    Generate all alarms from DATA_START until `now`.

    Day by day we:
      1. add random "background" alarms for every asset
      2. add a few known "episodes" (patterns we want the copilot to discover)
    Finally we add some currently ACTIVE alarms.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    rng = random.Random(seed)
    factory = AlarmFactory(rng, now)
    a = ASSETS_BY_ID

    day = DATA_START
    day_number = 0
    while day < now:
        # 1) background noise
        for asset in ASSETS:
            for template in ALARM_TEMPLATES[asset["asset_type"]]:
                if rng.random() < template["rate"]:
                    start = day + timedelta(minutes=rng.randint(0, 24 * 60 - 1))
                    factory.make(asset, template["alarm_name"], start)

        # 2a) Boiler Feed Pump 101 episode (every ~3 days):
        #     FCV-101 deviates -> BFP-101 discharge pressure high -> motor winding temp high
        if day_number % 3 == 0:
            t = day + timedelta(hours=rng.randint(6, 20), minutes=rng.randint(0, 59))
            factory.make(a["AST-FCV-101"], "Valve Position Deviation", t, severity="medium")
            factory.make(
                a["AST-BFP-101"],
                "High Discharge Pressure",
                t + timedelta(minutes=3),
                severity=rng.choice(["high", "critical"]),
            )
            if rng.random() < 0.6:
                factory.make(a["AST-MTR-101"], "High Winding Temperature", t + timedelta(minutes=9), severity="high")
            if rng.random() < 0.4:
                factory.make(a["AST-BFP-101"], "High Bearing Temperature", t + timedelta(minutes=12), severity="high")

        # 2b) Gas compressor K-501 episode (every ~4 days):
        #     cooler E-501 outlet temp high -> K-501 discharge pressure/temperature high
        if day_number % 4 == 1:
            t = day + timedelta(hours=rng.randint(8, 18), minutes=rng.randint(0, 59))
            factory.make(a["AST-EXC-501"], "High Outlet Temperature", t, severity="high")
            factory.make(
                a["AST-GCK-501"],
                "High Discharge Pressure",
                t + timedelta(minutes=5),
                severity=rng.choice(["high", "critical"]),
            )
            factory.make(a["AST-GCK-501"], "High Discharge Temperature", t + timedelta(minutes=7), severity="high")

        # 2c) Motor M-501 trip episode (every ~10 days):
        #     lube oil pressure low -> motor trip
        if day_number % 10 == 5:
            t = day + timedelta(hours=rng.randint(0, 23), minutes=rng.randint(0, 59))
            factory.make(a["AST-LOP-501"], "Low Lube Oil Pressure", t, severity="high")
            factory.make(a["AST-MTR-501"], "Motor Trip", t + timedelta(minutes=4), severity="critical")

        # 2d) Unit 2 alarm flood (every ~15 days): many alarms within a few minutes
        if day_number % 15 == 7:
            t = day + timedelta(hours=rng.randint(1, 22))
            for i in range(14):
                asset = a["AST-BLR-201"] if i % 2 == 0 else a["AST-SDR-201"]
                name = "High Flue Gas Temperature" if i % 2 == 0 else "Low Drum Level"
                factory.make(asset, name, t + timedelta(seconds=30 * i), duration_s=40)

        day += timedelta(days=1)
        day_number += 1

    # 3) Alarms that are active right now (so "show active alarms" questions work)
    active_list = [
        ("AST-BFP-101", "High Discharge Pressure", "critical", 2),
        ("AST-FCV-101", "Valve Position Deviation", "medium", 2.1),
        ("AST-BFP-102", "High Bearing Temperature", "critical", 5),
        ("AST-BFP-102", "High Vibration", "high", 4.5),
        ("AST-MTR-102", "High Winding Temperature", "high", 4),
        ("AST-GCK-501", "High Discharge Pressure", "critical", 1),
        ("AST-EXC-501", "High Outlet Temperature", "high", 1.2),
        ("AST-MTR-501", "Motor Trip", "high", 8),
        ("AST-SDR-201", "Low Drum Level", "high", 3),
        ("AST-ACP-401", "High Discharge Temperature", "medium", 6),
    ]
    for asset_id, alarm_name, severity, hours_ago in active_list:
        start = now - timedelta(hours=hours_ago)
        factory.make(a[asset_id], alarm_name, start, severity=severity, active=True)

    alarms = factory.alarms
    alarms.sort(key=lambda item: item["start_time"])
    return alarms
