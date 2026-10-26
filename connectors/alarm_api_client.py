"""HTTP client for the Alarm API (auth, trace headers, timeout, retries, error mapping)."""

import asyncio
import os
import time
import uuid

import httpx
from dotenv import load_dotenv

load_dotenv()


# Status codes that are worth retrying (temporary problems): 429 and every 5xx
def is_retryable(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


ERROR_CODES = {
    400: "INVALID_INPUT",
    401: "AUTH_FAILED",
    403: "AUTH_FAILED",
    404: "NOT_FOUND",
    422: "INVALID_INPUT",
    429: "RATE_LIMITED",
}


class AlarmApiError(Exception):
    """A clean error that can be shown to the user / LLM."""

    def __init__(
        self, code: str, message: str, status_code: int | None = None, trace_id: str | None = None, attempts: int = 1
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.trace_id = trace_id
        self.attempts = attempts

    def __str__(self):
        return (
            f"[{self.code}] {self.message} "
            f"(status={self.status_code}, attempts={self.attempts}, trace_id={self.trace_id})"
        )


class AlarmApiClient:
    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout_seconds: float | None = None,
        max_retries: int | None = None,
        backoff_seconds: float = 0.3,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = (base_url or os.getenv("ALARM_API_BASE_URL", "http://localhost:8000")).rstrip("/")
        self.token = token if token is not None else os.getenv("ALARM_API_TOKEN", "demo-token")
        self.timeout_seconds = timeout_seconds or float(os.getenv("ALARM_API_TIMEOUT_SECONDS", "10"))
        self.max_retries = max_retries if max_retries is not None else int(os.getenv("ALARM_API_MAX_RETRIES", "2"))
        self.backoff_seconds = backoff_seconds
        self.transport = transport  # only used by tests (httpx.MockTransport)

    # ---------------------------------
    # Core request with retry + errors
    # ---------------------------------

    def build_headers(self, trace_id: str) -> dict:
        headers = {
            "Accept": "application/json",
            "trace_id": trace_id,
            "x-trace-id": trace_id,
            "x-client-id": "alarm-mcp-server",
            "x-metadata-tag": "copilot",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def request(
        self, method: str, path: str, params: dict | None = None, body: dict | None = None, trace_id: str | None = None
    ):
        """
        Returns (data, meta). `meta` tells the caller how the call went:
        status code, number of attempts, duration and trace id.
        """
        trace_id = trace_id or f"mcp-{uuid.uuid4().hex[:12]}"
        headers = self.build_headers(trace_id)
        # Drop empty query params so the API gets a clean URL
        params = {k: v for k, v in (params or {}).items() if v is not None}

        started = time.perf_counter()
        attempt = 0
        last_error = None

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self.timeout_seconds, transport=self.transport
        ) as client:
            while attempt <= self.max_retries:
                attempt += 1
                wait_seconds = self.backoff_seconds * (2 ** (attempt - 1))  # 0.3s, 0.6s, 1.2s ...
                try:
                    response = await client.request(method, path, params=params, json=body, headers=headers)
                except httpx.TimeoutException:
                    last_error = AlarmApiError(
                        "TIMEOUT", f"Alarm API did not answer within {self.timeout_seconds}s", None, trace_id, attempt
                    )
                except httpx.RequestError as error:
                    last_error = AlarmApiError(
                        "CONNECTION_FAILED",
                        f"Could not reach Alarm API: {type(error).__name__}",
                        None,
                        trace_id,
                        attempt,
                    )
                else:
                    if response.status_code < 400:
                        meta = {
                            "trace_id": response.headers.get("trace_id", trace_id),
                            "status_code": response.status_code,
                            "attempts": attempt,
                            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                        }
                        return response.json(), meta

                    last_error = self.to_error(response, trace_id, attempt)
                    if not is_retryable(response.status_code):
                        raise last_error  # 4xx errors will not get better with a retry

                    # the API may tell us how long to wait (429 Too Many Requests)
                    retry_after = response.headers.get("Retry-After", "")
                    if retry_after.isdigit():
                        wait_seconds = min(float(retry_after), 5.0)

                # wait a bit before the next try
                if attempt <= self.max_retries:
                    await asyncio.sleep(wait_seconds)

        raise last_error

    @staticmethod
    def to_error(response: httpx.Response, trace_id: str, attempt: int) -> AlarmApiError:
        try:
            payload = response.json().get("error", {})
            message = payload.get("message", response.text[:200])
            details = payload.get("details")
            if details:
                message += " - " + "; ".join(f"{d['field']}: {d['message']}" for d in details[:3])
        except ValueError:
            message = response.text[:200] or "Unknown error"
        code = ERROR_CODES.get(response.status_code, "UPSTREAM_ERROR")
        return AlarmApiError(code, message, response.status_code, trace_id, attempt)

    # ---------------------------------
    # One small method per API endpoint
    # ---------------------------------

    async def search_assets(self, query, site=None, unit=None, limit=10, trace_id=None):
        return await self.request(
            "GET",
            "/assets/search",
            params={"query": query, "site": site, "unit": unit, "limit": limit},
            trace_id=trace_id,
        )

    async def get_asset_metadata(self, asset_id, trace_id=None):
        return await self.request("GET", f"/assets/{asset_id}/metadata", trace_id=trace_id)

    async def get_alarms(self, params: dict, trace_id=None):
        return await self.request("GET", "/alarms", params=params, trace_id=trace_id)

    async def get_all_alarm_pages(self, params: dict, max_pages: int = 5, trace_id=None):
        """Follows pagination until there are no more pages (or max_pages is reached)."""
        all_rows = []
        page = 1
        total_attempts = 0
        while True:
            data, meta = await self.get_alarms({**params, "page": page}, trace_id=trace_id)
            all_rows.extend(data["data"])
            total_attempts += meta["attempts"]
            if not data["pagination"]["has_next"] or page >= max_pages:
                break
            page += 1
        meta["attempts"] = total_attempts
        meta["pages_fetched"] = page
        pagination = data["pagination"]
        pagination["truncated"] = pagination["has_next"]
        return {"data": all_rows, "pagination": pagination}, meta

    async def get_alarm(self, alarm_id, trace_id=None):
        return await self.request("GET", f"/alarms/{alarm_id}", trace_id=trace_id)

    async def alarm_summary(self, body: dict, trace_id=None):
        return await self.request("POST", "/alarms/summary", body=body, trace_id=trace_id)

    async def alarm_trends(self, body: dict, trace_id=None):
        return await self.request("POST", "/alarms/trends", body=body, trace_id=trace_id)

    async def alarm_correlation(self, body: dict, trace_id=None):
        return await self.request("POST", "/alarms/correlation", body=body, trace_id=trace_id)

    async def priority_score(self, alarm_id, trace_id=None):
        return await self.request("POST", "/alarms/priority-score", body={"alarm_id": alarm_id}, trace_id=trace_id)

    async def operator_recommendations(self, body: dict, trace_id=None):
        return await self.request("POST", "/recommendations/operator-actions", body=body, trace_id=trace_id)

    async def health(self):
        return await self.request("GET", "/health")
