# API Integration – Alarm Management API

## Where the contract came from

The Postman collections in `postman/` (copied unchanged from the assignment package) define the endpoints, request bodies,
the bearer auth, the trace headers and the chaining flows. They do not contain response examples, so the response shapes
below are my design, chosen so that every Postman test script works (`body.results[0].asset_id`, `body.data[0].alarm_id`,
`body.calculation_id`, `body.flood_windows[0].start`).

Simulator: `apps/alarm_simulator/main.py` (routes, auth, middleware) + `analytics.py` (logic) + `data.py` (synthetic data).

## Conventions

| Topic | Implementation |
|---|---|
| Auth | `Authorization: Bearer <ALARM_API_TOKEN>` on every endpoint except `/health`. Missing/wrong → `401 {"error":{"code":"UNAUTHORIZED"}}` |
| Trace | Request headers `trace_id` (Postman) or `x-trace-id`, plus `x-client-id`, `x-metadata-tag`. Echoed in response headers and logged. Generated when missing. |
| Errors | One shape: `{"error": {"code", "message", "details?"}}`. 400 `BAD_REQUEST`, 401 `UNAUTHORIZED`, 404 `NOT_FOUND`, 422 `VALIDATION_ERROR`, 503 `SERVICE_UNAVAILABLE` (chaos) |
| Pagination | `page`, `page_size` (1–500) → `pagination: {page, page_size, total, total_pages, has_next}` |
| Time | ISO-8601 UTC (`2026-05-01T00:00:00Z`). `time_range.start_time` must be before `end_time` |
| Logs | One JSON line per request: method, path, status, duration_ms, trace_id, client_id, metadata_tag |

## Endpoints

| # | Method & path | Main inputs | Main output |
|---|---|---|---|
| 0 | `GET /health` | – | `{status, assets, alarms}` |
| 1 | `GET /assets/search` | `query`, `site?`, `unit?`, `limit`, `page` | `{query, results:[{asset_id, asset_name, asset_type, site, unit, criticality, match_score}], pagination}` |
| 2 | `GET /assets/{asset_id}/metadata` | – | asset fields + `operating_limits` + `related_assets[{asset_id, asset_name, asset_type, relationship}]` |
| 3 | `GET /alarms` | `asset_id/site/unit`, `status`, `severity[]`, `start_time`, `end_time`, `page`, `page_size`, `sort_by`, `sort_order` | `{data:[alarm], pagination}` |
| 4 | `GET /alarms/{alarm_id}` | – | alarm |
| 5 | `POST /alarms/summary` | scope + `time_range`, `severity`, `alarm_types`, `group_by`, `kpis` | `{total_alarms, overall, groups[], time_range}` |
| 6 | `POST /alarms/trends` | scope + `time_range`, `bucket`, `metrics` | `{bucket, series[], trend_direction}` |
| 7 | `POST /alarms/correlation` | `asset_ids`, `time_range`, `lag_window_minutes`, `severity_threshold`, `min_support` | `{assets_in_scope, events_analyzed, correlated_pairs[{leading_alarm, following_alarm, support, confidence, avg_lag_minutes}]}` |
| 8 | `POST /alarms/flood-analysis` | scope + `time_range`, `threshold_count`, `rolling_window_minutes` | `{total_alarms, flood_count, percent_time_in_flood, flood_windows[{start, end, alarm_count, assets, top_alarms}]}` |
| 9 | `POST /alarms/rationalization-candidates` | scope + `time_range`, `recurrence_threshold`, `stale_minutes_threshold` | `{candidate_count, candidates[{..., reasons, rationalization_score}]}` |
| 10 | `POST /alarms/priority-score` | `alarm_id` | `{priority_score, priority_level, factors[], explanation}` |
| 11 | `POST /recommendations/operator-actions` | `alarm_id`, `include_related`, `include_asset_context`, `include_historical_pattern` | `{recommended_actions[], related_assets_to_check[], asset_context, historical_pattern}` |
| 12 | `POST /calculation-code/generate` | `calculation_type`, `filters` | `{calculation_id, generated_code, status}` |
| 13 | `POST /calculation-code/execute` | `calculation_id`, `filters` | `{result:{value, unit, details}}` |
| 14 | `GET /analytics/kpi-definitions` | – | `{kpis[]}` |
| – | `POST /admin/chaos` | `failure_rate`, `latency_ms`, `fail_paths`, `status_code` | demo/test helper to force failures |

Alarm object: `alarm_id, asset_id, asset_name, site, unit, alarm_name, alarm_code, alarm_type (process|safety|device), severity (low|medium|high|critical), status (active|acknowledged|cleared), start_time, end_time, ack_time, ack_delay_seconds, duration_seconds, measure_unit, description`.

## Business rules (short)

- **Recurring rate** – share of alarms where the same alarm fired on the same asset within the previous 24 h.
- **Correlation** – co-occurrence: for every alarm A, alarms B starting within the lag window after A are counted; pairs with support ≥ `min_support` are returned with `confidence = support / count(A)`. Related assets of the requested assets are included.
- **Priority score** – severity (10–40) + asset criticality (5–20) + recurrence in 30 days (≤20) + active (10) + safety type (10), capped at 100. P1 ≥ 75, P2 ≥ 55, P3 ≥ 35, else P4.
- **Recommendations** – rule table per alarm name, with equipment-specific overrides. One pump rule ("reset the trip and restart the pump") deliberately disagrees with SOP-BFP-001 so the copilot can show conflict detection.

## How the MCP server uses the API

| MCP tool | API call(s) |
|---|---|
| `search_assets` | 1 |
| `get_asset_metadata` | 2 |
| `get_alarms` | 3 (repeated per page when `fetch_all_pages`, max 5 pages) |
| `get_alarm_details` | 4 |
| `get_alarm_summary` | 5 |
| `get_alarm_trends` | 6 |
| `correlate_alarms` | 7 |
| `score_alarm_priority` | 10 |
| `get_operator_recommendations` | 11 |

Endpoints 8, 9, 12–14 are implemented in the simulator (so all Postman collections pass) but not exposed as MCP tools, because the investigation use case does not need them. Adding one is a ~15-line tool function.

## Verified with Postman (newman)

| Collection | Requests | Result |
|---|---|---|
| Alarm-API-Simulator (E2E baseline) | 15 | all passed |
| Alarm-API-Scenarios | 15 | all passed |
| Alarm-API-Chaining (10 chains) | 32 | all passed |
| Alarm-API-Contract-Tests (mine: auth, trace echo, pagination, 404/422/400, shapes) | 12 / 23 assertions | all passed |

Raw output: `docs/test-evidence/newman-*.txt` and JUnit XML.
