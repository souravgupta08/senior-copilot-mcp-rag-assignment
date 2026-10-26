"""
Planner: reads the user's question and decides WHAT to do.

It is rule based (keywords + regular expressions), so it is fast, free and
easy to test. The output is a "plan" dict that the workflow follows.

Example:
    "Investigate recurring high-severity alarms for Boiler Feed Pump 101 over the last 90 days"
    -> intent="investigation", asset_query="Boiler Feed Pump 101", days=90,
       severity=["high","critical"], steps=[alarms, metadata, summary, trends, correlation, ...]
"""

import re
from datetime import datetime, timedelta, timezone

# Which tool steps each intent needs. RAG is always added.
INTENT_STEPS = {
    "investigation": ["alarms", "metadata", "summary", "trends", "correlation", "priority", "recommendations"],
    "recurring_causes": ["alarms", "metadata", "summary", "trends", "correlation", "recommendations"],
    "active_alarms": ["alarms", "metadata", "priority", "recommendations"],
    "highest_priority": ["alarms", "priority", "recommendations", "metadata"],
    "related_assets": ["alarms", "metadata", "correlation", "recommendations"],
    "procedure": ["alarms", "metadata", "recommendations"],
    "consistency": ["alarms", "metadata", "recommendations"],
}

EQUIPMENT_WORDS = r"(?:pump|motor|compressor|valve|tank|boiler|drum|tower|dryer|cooler|exchanger)"
PREFIX_WORDS = (
    r"(?:boiler|feed|bfp|gas|air|cooling|water|compressor|lube|oil|feedwater|control|steam|deaerator|discharge)"
)

ASSET_PATTERN = re.compile(rf"\b((?:{PREFIX_WORDS}\s+){{0,3}}{EQUIPMENT_WORDS})s?\b", re.IGNORECASE)
TAG_PATTERN = re.compile(r"\b(AST-[A-Z]{3}-\d{3}|[A-Z]{1,3}-\d{3})\b")
SITE_PATTERN = re.compile(r"\b(?:in|at|for|across)\s+(?:the\s+)?([A-Z][a-z]+[A-Z][A-Za-z]+)\b")
UNIT_PATTERN = re.compile(r"\b(unit\s*\d+)\b", re.IGNORECASE)
DAYS_PATTERN = re.compile(r"\b(?:last|past)\s+(\d+)\s*(day|week|month|year)s?\b", re.IGNORECASE)
MAX_DAYS = 365
# Short upper-case words that are NOT part of an asset name
NOT_ASSET_WORDS = {"SOP", "OK", "KPI", "API", "MCP", "RCA", "UTC", "DCS", "AND", "THE", "FOR"}
ALARM_ID_PATTERN = re.compile(r"\bALM-\d{6}\b")
DOMAIN_WORDS = re.compile(
    r"alarm|asset|pump|motor|compressor|valve|boiler|drum|cooler|tank|procedure|sop|priority|investigat|"
    r"inspect|recommend|cause|trip|pressure|temperature|vibration|manual|related|active|critical|maintenance|"
    r"unit\s*\d|plant|refinery",
    re.IGNORECASE,
)


def detect_intent(text: str) -> str:
    t = text.lower()
    if re.search(r"highest[- ]priority|most urgent|top priority|prioriti[sz]e", t):
        return "highest_priority"
    if re.search(
        r"consistent|consistency|agree with|match(es)? the (manual|procedure)|compare .*(manual|procedure)", t
    ):
        return "consistency"
    if re.search(r"related assets?|what (other )?assets?|which assets? should|should be inspected|inspect", t):
        return "related_assets"
    if re.search(r"which (operating )?procedure|what procedure|\bsop\b|procedure applies", t):
        return "procedure"
    if (
        re.search(r"\bwhy\b|repeated|repeatedly|keeps? (coming|happening|occurring)|root cause", t)
        and "investigate" not in t
    ):
        return "recurring_causes"
    if re.search(r"\bactive\b|\bcurrent\b|\bopen\b|right now", t) and "investigate" not in t:
        return "active_alarms"
    return "investigation"


def looks_like_identifier(word: str) -> bool:
    """'101', 'K-501', 'XYZ' look like parts of an asset name; 'and', 'alarms' do not."""
    word = word.strip(",.?!")
    if not word or word.upper() in NOT_ASSET_WORDS:
        return False
    return any(ch.isdigit() for ch in word) or (word.isupper() and len(word) <= 4)


def extract_asset_query(text: str) -> str | None:
    """Find something that looks like an asset name ('Boiler Feed Pump 101', 'K-501', 'compressor')."""
    tag = TAG_PATTERN.search(text)
    generic = None
    # Look at every equipment mention; a mention with an id ("Pump 101") wins over a generic one ("pump")
    for match in ASSET_PATTERN.finditer(text):
        name = match.group(1).strip()
        # take up to two identifier-like words after the equipment word: "Pump 101", "Compressor K-501"
        ident = []
        for word in text[match.end(1) :].split()[:2]:
            if not looks_like_identifier(word):
                break
            ident.append(word.strip(",.?!"))
            if word[-1] in ",.?!":
                break  # punctuation ends the asset name: "pump 101, last 30 days"
        if ident:
            return f"{name} {' '.join(ident)}"
        generic = generic or name
    if tag:
        return tag.group(1)
    return generic


def extract_severity(text: str) -> list[str] | None:
    t = text.lower()
    if re.search(r"high[- ]severity|high and critical|severe", t):
        return ["high", "critical"]
    if "critical" in t:
        return ["critical"]
    return None


def extract_days(text: str, default: int = 90) -> tuple[int, bool, str | None]:
    """Returns (days, was_given_by_user, note). The note explains any adjustment we made."""
    match = DAYS_PATTERN.search(text)
    if not match:
        return default, False, None
    number, unit = int(match.group(1)), match.group(2).lower()
    days = number * {"day": 1, "week": 7, "month": 30, "year": 365}[unit]
    if days < 1:
        return 1, True, "A time range of 0 days is empty - using the last 1 day instead."
    if days > MAX_DAYS:
        return MAX_DAYS, True, f"Time range limited to the last {MAX_DAYS} days (you asked for {days})."
    return days, True, None


def to_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def make_plan(message: str, context: dict | None = None, now: datetime | None = None) -> dict:
    """
    Build the plan for one user message.
    `context` holds what we remember from earlier turns (last assets / alarm).
    """
    context = context or {}
    now = (now or datetime.now(timezone.utc)).replace(microsecond=0)

    intent = detect_intent(message)
    asset_query = extract_asset_query(message)
    site_match = SITE_PATTERN.search(message)
    unit_match = UNIT_PATTERN.search(message)
    alarm_id_match = ALARM_ID_PATTERN.search(message)
    days, days_given, days_note = extract_days(message)
    severity = extract_severity(message)

    status = None
    if intent in ("active_alarms", "highest_priority") or re.search(r"\bactive\b", message, re.IGNORECASE):
        status = "active"

    # Greetings or unrelated questions: ask the user what to investigate
    off_topic = not (DOMAIN_WORDS.search(message) or asset_query or site_match or unit_match or alarm_id_match)

    assumptions = []
    if not days_given and not off_topic:
        assumptions.append(f"No time range given - using the last {days} days.")
    if days_note:
        assumptions.append(days_note)

    used_context = False
    # A follow-up like "which procedure applies to this alarm?" reuses the previous asset
    if not off_topic and not asset_query and not site_match and not unit_match and context.get("assets"):
        used_context = True
        assumptions.append(
            "No asset named - continuing with "
            + ", ".join(a["asset_name"] for a in context["assets"])
            + " from the previous question."
        )

    # A generic equipment word ("motor") with a remembered asset of that type -> keep the remembered asset
    if asset_query and not re.search(r"\d", asset_query) and context.get("assets"):
        remembered = context["assets"][0]
        if (
            remembered["asset_type"].replace("_", " ") in asset_query.lower()
            or asset_query.lower() in remembered["asset_name"].lower()
        ):
            if re.search(r"\bthis\b|\bthat\b|\bsame\b", message, re.IGNORECASE):
                asset_query = None
                used_context = True
                assumptions.append(f"'this' interpreted as {remembered['asset_name']} from the previous question.")

    steps = list(INTENT_STEPS[intent])

    return {
        "intent": intent,
        "message": message,
        "asset_query": asset_query,
        "site": site_match.group(1) if site_match else None,
        "unit": "Unit " + re.sub(r"\D", "", unit_match.group(1)) if unit_match else None,  # "unit2" -> "Unit 2"
        "alarm_id": alarm_id_match.group(0) if alarm_id_match else (context.get("alarm_id") if used_context else None),
        "status": status,
        "severity": severity,
        "days": days,
        "start_time": to_iso(now - timedelta(days=days)),
        "end_time": to_iso(now),
        "use_context_assets": used_context,
        "off_topic": off_topic,
        "steps": steps + ["rag"],
        "assumptions": assumptions,
    }
