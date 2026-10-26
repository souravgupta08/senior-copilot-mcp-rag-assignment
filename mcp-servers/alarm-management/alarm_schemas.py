"""
Typed output schemas for the Alarm Management MCP tools.

FastMCP turns these Pydantic models into JSON "outputSchema" entries, so a
client can see exactly what each tool returns before calling it.
"""

from typing import Any

from pydantic import BaseModel, Field


class CallMeta(BaseModel):
    """How the underlying API call went (shown in the GUI trace)."""

    trace_id: str
    status_code: int
    attempts: int = Field(description="1 = first try worked, >1 = retries happened")
    duration_ms: float
    pages_fetched: int | None = None


class Pagination(BaseModel):
    page: int
    page_size: int
    total: int
    total_pages: int
    has_next: bool
    truncated: bool | None = None


# ---------- assets ----------


class AssetMatch(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    site: str
    unit: str
    criticality: str
    match_score: float


class AssetSearchResult(BaseModel):
    query: str
    results: list[AssetMatch]
    pagination: Pagination
    meta: CallMeta


class RelatedAsset(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    relationship: str


class AssetMetadataResult(BaseModel):
    asset_id: str
    asset_name: str
    asset_type: str
    site: str
    unit: str
    criticality: str
    manufacturer: str
    model: str
    install_date: str
    last_maintenance_date: str
    operating_limits: dict[str, Any]
    related_assets: list[RelatedAsset]
    meta: CallMeta


# ---------- alarms ----------


class Alarm(BaseModel):
    alarm_id: str
    asset_id: str
    asset_name: str
    site: str
    unit: str
    alarm_name: str
    alarm_code: str
    alarm_type: str
    severity: str
    status: str
    start_time: str
    end_time: str | None = None
    ack_time: str | None = None
    ack_delay_seconds: int | None = None
    duration_seconds: int | None = None
    description: str


class AlarmListResult(BaseModel):
    alarms: list[Alarm]
    pagination: Pagination
    meta: CallMeta


class AlarmDetailResult(BaseModel):
    alarm: Alarm
    meta: CallMeta


class AlarmSummaryResult(BaseModel):
    total_alarms: int
    overall: dict[str, Any]
    groups: list[dict[str, Any]]
    meta: CallMeta


class AlarmTrendResult(BaseModel):
    bucket: str
    trend_direction: str
    series: list[dict[str, Any]]
    meta: CallMeta


# ---------- advanced operations ----------


class AlarmRef(BaseModel):
    asset_id: str
    asset_name: str
    alarm_name: str


class CorrelatedPair(BaseModel):
    leading_alarm: AlarmRef
    following_alarm: AlarmRef
    support: int
    confidence: float
    avg_lag_minutes: float


class CorrelationResult(BaseModel):
    assets_in_scope: list[str]
    events_analyzed: int
    correlated_pairs: list[CorrelatedPair]
    meta: CallMeta


class PriorityFactor(BaseModel):
    factor: str
    value: Any
    points: int


class PriorityScoreResult(BaseModel):
    alarm_id: str
    priority_score: int
    priority_level: str
    factors: list[PriorityFactor]
    explanation: str
    meta: CallMeta


class RecommendedAction(BaseModel):
    step: int
    action: str
    urgency: str
    source: str


class OperatorRecommendationResult(BaseModel):
    alarm_id: str
    alarm_name: str
    asset_id: str
    asset_name: str
    severity: str
    recommended_actions: list[RecommendedAction]
    related_assets_to_check: list[dict[str, Any]] | None = None
    asset_context: dict[str, Any] | None = None
    historical_pattern: dict[str, Any] | None = None
    meta: CallMeta
