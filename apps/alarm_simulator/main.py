"""
Alarm Management API simulator.

This is the "source system" our MCP server talks to. It was built from the
Postman collections in /postman (they are the API contract).

Run it:
    uvicorn apps.alarm_simulator.main:app --port 8000
"""

import asyncio
import json
import logging
import os
import random
import time
import uuid
from datetime import datetime, timezone
from typing import Literal

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from apps.alarm_simulator import analytics
from apps.alarm_simulator.data import ASSETS_BY_ID, build_alarms, parse_time

load_dotenv()

API_TOKEN = os.getenv("ALARM_API_TOKEN", "demo-token")

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("alarm-api")


# =========================
# App + data
# =========================

app = FastAPI(
    title="Alarm Management API Simulator",
    description="Simulated alarm management system used as the MCP server's source system",
    version="1.0.0",
)

ALARMS = build_alarms()
ALARMS_BY_ID = {alarm["alarm_id"]: alarm for alarm in ALARMS}

# "Chaos" settings let us demo retries and partial failures.
CHAOS = {
    "failure_rate": float(os.getenv("SIM_FAILURE_RATE", "0")),
    "latency_ms": int(os.getenv("SIM_LATENCY_MS", "0")),
    "fail_paths": [],
    "status_code": 503,
}


# =========================
# Middleware: trace headers, logging, chaos
# =========================


@app.middleware("http")
async def trace_and_log(request: Request, call_next):
    trace_id = request.headers.get("trace_id") or request.headers.get("x-trace-id") or f"sim-{uuid.uuid4().hex[:12]}"
    client_id = request.headers.get("x-client-id", "unknown")
    tag = request.headers.get("x-metadata-tag", "")
    started = time.perf_counter()

    path = request.url.path
    chaos_applies = not path.startswith(("/health", "/admin", "/docs", "/openapi"))

    if chaos_applies and CHAOS["latency_ms"]:
        await asyncio.sleep(CHAOS["latency_ms"] / 1000)

    if chaos_applies and (
        any(path.startswith(p) for p in CHAOS["fail_paths"]) or random.random() < CHAOS["failure_rate"]
    ):
        response = JSONResponse(
            status_code=CHAOS["status_code"],
            content={
                "error": {"code": "SERVICE_UNAVAILABLE", "message": "Simulated upstream failure", "trace_id": trace_id}
            },
        )
    else:
        response = await call_next(request)

    duration_ms = round((time.perf_counter() - started) * 1000, 1)
    response.headers["trace_id"] = trace_id
    response.headers["x-trace-id"] = trace_id
    response.headers["x-client-id"] = client_id

    # Structured log line (no tokens are logged)
    logger.info(
        json.dumps(
            {
                "service": "alarm-api",
                "method": request.method,
                "path": path,
                "status": response.status_code,
                "duration_ms": duration_ms,
                "trace_id": trace_id,
                "client_id": client_id,
                "metadata_tag": tag,
            }
        )
    )
    return response


# =========================
# Error handlers -> one consistent error shape
# =========================


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    code = {400: "BAD_REQUEST", 401: "UNAUTHORIZED", 404: "NOT_FOUND"}.get(exc.status_code, "ERROR")
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "message": exc.detail}},
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [{"field": ".".join(str(p) for p in e["loc"]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "message": "Invalid request", "details": details}},
    )


# =========================
# Auth
# =========================


def require_token(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token", headers={"WWW-Authenticate": "Bearer"})
    token = authorization.split(" ", 1)[1].strip()
    if token != API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid bearer token")


# =========================
# Request models
# =========================

Severity = Literal["low", "medium", "high", "critical"]


class TimeRange(BaseModel):
    start_time: str
    end_time: str

    def parsed(self):
        try:
            start, end = parse_time(self.start_time), parse_time(self.end_time)
        except ValueError as error:
            raise HTTPException(status_code=400, detail="time_range must use ISO-8601 timestamps") from error
        if start >= end:
            raise HTTPException(status_code=400, detail="time_range.start_time must be before end_time")
        return start, end


class Scope(BaseModel):
    asset_ids: list[str] | None = None
    site: str | None = None
    unit: str | None = None
    time_range: TimeRange

    def check_assets(self):
        for asset_id in self.asset_ids or []:
            if asset_id not in ASSETS_BY_ID:
                raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")


class SummaryRequest(Scope):
    severity: list[Severity] | None = None
    alarm_types: list[str] | None = None
    status: str | None = None
    group_by: list[str] = ["alarm_name"]
    kpis: list[str] = ["alarm_count"]


class TrendsRequest(Scope):
    bucket: Literal["hourly", "daily", "weekly"] = "daily"
    metrics: list[str] = ["alarm_count"]
    severity: list[Severity] | None = None


class CorrelationRequest(Scope):
    correlation_method: Literal["cooccurrence"] = "cooccurrence"
    lag_window_minutes: int = Field(default=15, ge=1, le=240)
    severity_threshold: Severity = "medium"
    min_support: int = Field(default=2, ge=1)


class FloodRequest(Scope):
    threshold_count: int = Field(default=10, ge=2)
    rolling_window_minutes: int = Field(default=10, ge=1, le=1440)


class RationalizationRequest(Scope):
    recurrence_threshold: int = Field(default=5, ge=1)
    stale_minutes_threshold: int = Field(default=180, ge=1)


class AlarmRef(BaseModel):
    alarm_id: str


class RecommendationRequest(BaseModel):
    alarm_id: str
    include_related: bool = True
    include_asset_context: bool = True
    include_historical_pattern: bool = True


class CalcFilters(BaseModel):
    site: str | None = None
    unit: str | None = None
    asset_ids: list[str] | None = None
    start_time: str
    end_time: str


class GenerateCalcRequest(BaseModel):
    calculation_type: str
    filters: CalcFilters


class ExecuteCalcRequest(BaseModel):
    calculation_id: str
    filters: CalcFilters


class ChaosRequest(BaseModel):
    failure_rate: float = Field(default=0.0, ge=0, le=1)
    latency_ms: int = Field(default=0, ge=0, le=60000)
    fail_paths: list[str] = []
    status_code: int = Field(default=503, ge=400, le=599)


# =========================
# Helpers
# =========================


def get_alarm_or_404(alarm_id: str) -> dict:
    alarm = ALARMS_BY_ID.get(alarm_id)
    if not alarm:
        raise HTTPException(status_code=404, detail=f"Alarm '{alarm_id}' not found")
    return alarm


def alarms_in_scope(scope: Scope, **extra):
    scope.check_assets()
    start, end = scope.time_range.parsed()
    return (
        analytics.filter_alarms(
            ALARMS, asset_ids=scope.asset_ids, site=scope.site, unit=scope.unit, start_time=start, end_time=end, **extra
        ),
        start,
        end,
    )


def check_allowed(values, allowed, field):
    bad = [v for v in values if v not in allowed]
    if bad:
        raise HTTPException(status_code=400, detail=f"Unsupported {field}: {bad}. Allowed: {allowed}")


# =========================
# Routes
# =========================


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "alarm-management-api-simulator",
        "assets": len(ASSETS_BY_ID),
        "alarms": len(ALARMS),
    }


@app.get("/assets/search", dependencies=[Depends(require_token)])
def search_assets(
    query: str = Query(min_length=1, max_length=100),
    site: str | None = None,
    unit: str | None = None,
    limit: int = Query(default=10, ge=1, le=100),
    page: int = Query(default=1, ge=1),
):
    results = analytics.search_assets(query, site=site, unit=unit)
    page_items, pagination = analytics.paginate(results, page, limit)
    return {"query": query, "results": page_items, "pagination": pagination}


@app.get("/assets/{asset_id}/metadata", dependencies=[Depends(require_token)])
def get_asset_metadata(asset_id: str):
    if asset_id not in ASSETS_BY_ID:
        raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' not found")
    return analytics.asset_metadata(asset_id)


@app.get("/alarms", dependencies=[Depends(require_token)])
def list_alarms(
    asset_id: str | None = None,
    site: str | None = None,
    unit: str | None = None,
    status: Literal["active", "acknowledged", "cleared"] | None = None,
    severity: list[Severity] | None = Query(default=None),
    start_time: str | None = None,
    end_time: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=500),
    sort_by: Literal["start_time", "severity"] = "start_time",
    sort_order: Literal["asc", "desc"] = "desc",
):
    try:
        start = parse_time(start_time) if start_time else None
        end = parse_time(end_time) if end_time else None
    except ValueError as error:
        raise HTTPException(status_code=400, detail="start_time/end_time must be ISO-8601 timestamps") from error

    rows = analytics.filter_alarms(
        ALARMS,
        asset_ids=[asset_id] if asset_id else None,
        site=site,
        unit=unit,
        status=status,
        severity=severity,
        start_time=start,
        end_time=end,
    )
    if sort_by == "severity":
        rows = sorted(rows, key=lambda a: (analytics.SEVERITY_ORDER[a["severity"]], a["start_time"]))
    else:
        rows = sorted(rows, key=lambda a: a["start_time"])
    if sort_order == "desc":
        rows = list(reversed(rows))

    page_items, pagination = analytics.paginate(rows, page, page_size)
    return {"data": page_items, "pagination": pagination}


@app.get("/alarms/{alarm_id}", dependencies=[Depends(require_token)])
def get_alarm(alarm_id: str):
    return get_alarm_or_404(alarm_id)


@app.post("/alarms/summary", dependencies=[Depends(require_token)])
def summary(body: SummaryRequest):
    check_allowed(body.group_by, analytics.SUPPORTED_GROUP_BY, "group_by")
    check_allowed(body.kpis, analytics.SUPPORTED_KPIS, "kpis")
    rows, _, _ = alarms_in_scope(body, severity=body.severity, alarm_types=body.alarm_types, status=body.status)
    result = analytics.alarm_summary(rows, body.group_by, body.kpis)
    result["time_range"] = body.time_range.model_dump()
    return result


@app.post("/alarms/trends", dependencies=[Depends(require_token)])
def trends(body: TrendsRequest):
    check_allowed(body.metrics, analytics.SUPPORTED_KPIS, "metrics")
    rows, start, end = alarms_in_scope(body, severity=body.severity)
    return analytics.alarm_trends(rows, start, end, body.bucket, body.metrics)


@app.post("/alarms/correlation", dependencies=[Depends(require_token)])
def correlation(body: CorrelationRequest):
    if not body.asset_ids:
        raise HTTPException(status_code=400, detail="asset_ids is required for correlation")
    rows_scope = Scope(time_range=body.time_range, asset_ids=body.asset_ids)
    rows_scope.check_assets()
    start, end = body.time_range.parsed()
    rows = analytics.filter_alarms(ALARMS, start_time=start, end_time=end)
    result = analytics.correlate(
        rows, body.asset_ids, body.lag_window_minutes, body.severity_threshold, body.min_support
    )
    result["method"] = body.correlation_method
    return result


@app.post("/alarms/flood-analysis", dependencies=[Depends(require_token)])
def flood(body: FloodRequest):
    rows, start, end = alarms_in_scope(body)
    return analytics.flood_analysis(rows, body.threshold_count, body.rolling_window_minutes, start, end)


@app.post("/alarms/rationalization-candidates", dependencies=[Depends(require_token)])
def rationalization(body: RationalizationRequest):
    rows, _, _ = alarms_in_scope(body)
    candidates = analytics.rationalization_candidates(
        rows, body.recurrence_threshold, body.stale_minutes_threshold, datetime.now(timezone.utc)
    )
    return {"candidate_count": len(candidates), "candidates": candidates}


@app.post("/alarms/priority-score", dependencies=[Depends(require_token)])
def priority(body: AlarmRef):
    alarm = get_alarm_or_404(body.alarm_id)
    return analytics.priority_score(alarm, ALARMS)


@app.post("/recommendations/operator-actions", dependencies=[Depends(require_token)])
def recommendations(body: RecommendationRequest):
    alarm = get_alarm_or_404(body.alarm_id)
    return analytics.operator_recommendations(
        alarm, ALARMS, body.include_related, body.include_asset_context, body.include_historical_pattern
    )


@app.post("/calculation-code/generate", dependencies=[Depends(require_token)])
def generate_calculation(body: GenerateCalcRequest):
    allowed = [d["calculation_type"] for d in analytics.KPI_DEFINITIONS]
    if body.calculation_type not in allowed:
        raise HTTPException(status_code=400, detail=f"Unknown calculation_type. Allowed: {allowed}")
    return analytics.generate_calculation(body.calculation_type, body.filters.model_dump(exclude_none=True))


@app.post("/calculation-code/execute", dependencies=[Depends(require_token)])
def execute_calculation(body: ExecuteCalcRequest):
    if body.calculation_id not in analytics.CALCULATIONS:
        raise HTTPException(status_code=404, detail=f"Calculation '{body.calculation_id}' not found")
    f = body.filters
    scope = Scope(
        asset_ids=f.asset_ids,
        site=f.site,
        unit=f.unit,
        time_range=TimeRange(start_time=f.start_time, end_time=f.end_time),
    )
    rows, start, end = alarms_in_scope(scope)
    return analytics.execute_calculation(body.calculation_id, rows, start, end)


@app.get("/analytics/kpi-definitions", dependencies=[Depends(require_token)])
def kpi_definitions():
    return {"kpis": analytics.KPI_DEFINITIONS}


# Admin endpoint used only for demos/tests of failure handling
@app.post("/admin/chaos", dependencies=[Depends(require_token)])
def set_chaos(body: ChaosRequest):
    CHAOS.update(body.model_dump())
    return {"chaos": CHAOS}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("apps.alarm_simulator.main:app", host="127.0.0.1", port=8000, reload=False)
