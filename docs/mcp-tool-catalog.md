# MCP Tool Catalog - Alarm Management MCP Server

_Generated from the running server by `python scripts/generate_tool_catalog.py`._

Server: `mcp-servers/alarm-management/alarm_mcp_server.py` (FastMCP). Transports: stdio (default) or streamable HTTP on `http://<host>:9000/mcp`.

## Behaviour shared by every tool

| Topic | Behaviour |
|---|---|
| Authentication | The server reads `ALARM_API_TOKEN` from its environment and sends `Authorization: Bearer <token>` to the Alarm API. The token is never returned, logged or put in errors. MCP clients do not need (and never see) the API token. |
| Input validation | Pydantic types on every argument (id patterns like `^AST-[A-Z]{3}-\d{3}$`, ISO timestamps, enums, min/max). The copilot also validates against the published JSON schema before calling. Business checks (start < end, at least one scope filter) raise `[INVALID_INPUT]`. |
| Output validation | Every tool returns a Pydantic model -> published `outputSchema` + `structuredContent`. |
| Trace metadata | Optional `trace_id` argument. Forwarded to the API as `trace_id` / `x-trace-id` headers together with `x-client-id: alarm-mcp-server`. Returned in `meta.trace_id`. |
| Timeout | `ALARM_API_TIMEOUT_SECONDS` (default 10 s) per HTTP attempt. The copilot adds an overall `MCP_TOOL_TIMEOUT_SECONDS` (default 30 s) per tool call. |
| Retry | Up to `ALARM_API_MAX_RETRIES` (default 2) retries with exponential back-off (0.3 s, 0.6 s) on timeouts, connection errors, 429 and any 5xx (a `Retry-After` header is honoured, max 5 s). Other 4xx errors are not retried. `meta.attempts` shows how many tries were needed. |
| Errors | API errors become MCP tool errors (`isError=true`) with text `[CODE] message (status=..., attempts=..., trace_id=...)`. Codes: `INVALID_INPUT` (400/422), `AUTH_FAILED` (401/403), `NOT_FOUND` (404), `RATE_LIMITED` (429), `UPSTREAM_ERROR` (5xx), `TIMEOUT`, `CONNECTION_FAILED`. |
| Logging | One JSON line per call on stderr: tool, outcome, api_status, attempts, retries, trace_id, duration_ms. |

Example error (`get_asset_metadata` with an unknown id):

```text
Error executing tool get_asset_metadata: [NOT_FOUND] Asset 'AST-XXX-999' not found (status=404, attempts=1, trace_id=catalog)
```

## Tools

### `search_assets`

**Purpose:** Resolve a name like 'Boiler Feed Pump 101' to an asset id.  
**Description shown to clients:** Find assets by name or keyword and return their asset ids (best match first).  
**Underlying API operation:** `GET /assets/search`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "query": {
      "description": "Asset name or keyword, e.g. 'Boiler Feed Pump 101'",
      "maxLength": 100,
      "minLength": 2,
      "title": "Query",
      "type": "string"
    },
    "site": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional site filter, e.g. NorthPlant",
      "title": "Site"
    },
    "unit": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional unit filter, e.g. 'Unit 1'",
      "title": "Unit"
    },
    "limit": {
      "default": 5,
      "maximum": 50,
      "minimum": 1,
      "title": "Limit",
      "type": "integer"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "query"
  ],
  "title": "search_assetsArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "AssetMatch": {
      "properties": {
        "asset_id": {
          "title": "Asset Id",
          "type": "string"
        },
        "asset_name": {
          "title": "Asset Name",
          "type": "string"
        },
        "asset_type": {
          "title": "Asset Type",
          "type": "string"
        },
        "site": {
          "title": "Site",
          "type": "string"
        },
        "unit": {
          "title": "Unit",
          "type": "string"
        },
        "criticality": {
          "title": "Criticality",
          "type": "string"
        },
        "match_score": {
          "title": "Match Score",
          "type": "number"
        }
      },
      "required": [
        "asset_id",
        "asset_name",
        "asset_type",
        "site",
        "unit",
        "criticality",
        "match_score"
      ],
      "title": "AssetMatch",
      "type": "object"
    },
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    },
    "Pagination": {
      "properties": {
        "page": {
          "title": "Page",
          "type": "integer"
        },
        "page_size": {
          "title": "Page Size",
          "type": "integer"
        },
        "total": {
          "title": "Total",
          "type": "integer"
        },
        "total_pages": {
          "title": "Total Pages",
          "type": "integer"
        },
        "has_next": {
          "title": "Has Next",
          "type": "boolean"
        },
        "truncated": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Truncated"
        }
      },
      "required": [
        "page",
        "page_size",
        "total",
        "total_pages",
        "has_next"
      ],
      "title": "Pagination",
      "type": "object"
    }
  },
  "properties": {
    "query": {
      "title": "Query",
      "type": "string"
    },
    "results": {
      "items": {
        "$ref": "#/$defs/AssetMatch"
      },
      "title": "Results",
      "type": "array"
    },
    "pagination": {
      "$ref": "#/$defs/Pagination"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "query",
    "results",
    "pagination",
    "meta"
  ],
  "title": "AssetSearchResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "search_assets",
  "arguments": {
    "query": "Boiler Feed Pump 101",
    "limit": 2
  }
}
```

**Example response** (long lists shortened)

```json
{
  "query": "Boiler Feed Pump 101",
  "results": [
    {
      "asset_id": "AST-BFP-101",
      "asset_name": "Boiler Feed Pump 101",
      "asset_type": "pump",
      "site": "NorthPlant",
      "unit": "Unit 1",
      "criticality": "high",
      "match_score": 1.0
    },
    {
      "asset_id": "AST-BFP-102",
      "asset_name": "Boiler Feed Pump 102",
      "asset_type": "pump",
      "site": "NorthPlant",
      "unit": "Unit 1",
      "criticality": "high",
      "match_score": 0.8
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 2,
    "total": 8,
    "total_pages": 4,
    "has_next": true,
    "truncated": null
  },
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 14.9,
    "pages_fetched": null
  }
}
```

### `get_asset_metadata`

**Purpose:** Asset context and related assets.  
**Description shown to clients:** Get asset details: type, criticality, operating limits, maintenance date and related assets.  
**Underlying API operation:** `GET /assets/{asset_id}/metadata`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "asset_id": {
      "description": "Asset id, e.g. AST-BFP-101",
      "pattern": "^AST-[A-Z]{3}-\\d{3}$",
      "title": "Asset Id",
      "type": "string"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "asset_id"
  ],
  "title": "get_asset_metadataArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    },
    "RelatedAsset": {
      "properties": {
        "asset_id": {
          "title": "Asset Id",
          "type": "string"
        },
        "asset_name": {
          "title": "Asset Name",
          "type": "string"
        },
        "asset_type": {
          "title": "Asset Type",
          "type": "string"
        },
        "relationship": {
          "title": "Relationship",
          "type": "string"
        }
      },
      "required": [
        "asset_id",
        "asset_name",
        "asset_type",
        "relationship"
      ],
      "title": "RelatedAsset",
      "type": "object"
    }
  },
  "properties": {
    "asset_id": {
      "title": "Asset Id",
      "type": "string"
    },
    "asset_name": {
      "title": "Asset Name",
      "type": "string"
    },
    "asset_type": {
      "title": "Asset Type",
      "type": "string"
    },
    "site": {
      "title": "Site",
      "type": "string"
    },
    "unit": {
      "title": "Unit",
      "type": "string"
    },
    "criticality": {
      "title": "Criticality",
      "type": "string"
    },
    "manufacturer": {
      "title": "Manufacturer",
      "type": "string"
    },
    "model": {
      "title": "Model",
      "type": "string"
    },
    "install_date": {
      "title": "Install Date",
      "type": "string"
    },
    "last_maintenance_date": {
      "title": "Last Maintenance Date",
      "type": "string"
    },
    "operating_limits": {
      "additionalProperties": true,
      "title": "Operating Limits",
      "type": "object"
    },
    "related_assets": {
      "items": {
        "$ref": "#/$defs/RelatedAsset"
      },
      "title": "Related Assets",
      "type": "array"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "asset_id",
    "asset_name",
    "asset_type",
    "site",
    "unit",
    "criticality",
    "manufacturer",
    "model",
    "install_date",
    "last_maintenance_date",
    "operating_limits",
    "related_assets",
    "meta"
  ],
  "title": "AssetMetadataResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "get_asset_metadata",
  "arguments": {
    "asset_id": "AST-BFP-101"
  }
}
```

**Example response** (long lists shortened)

```json
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
  "operating_limits": {
    "discharge_pressure_bar": 120,
    "bearing_temp_c": 85,
    "vibration_mm_s": 7.1
  },
  "related_assets": [
    {
      "asset_id": "AST-MTR-101",
      "asset_name": "BFP Motor 101",
      "asset_type": "motor",
      "relationship": "driven_by"
    },
    {
      "asset_id": "AST-FCV-101",
      "asset_name": "Feedwater Control Valve FCV-101",
      "asset_type": "valve",
      "relationship": "downstream_valve"
    },
    {
      "asset_id": "AST-DEA-101",
      "asset_name": "Deaerator Tank D-101",
      "asset_type": "vessel",
      "relationship": "suction_source"
    }
  ],
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 14.9,
    "pages_fetched": null
  }
}
```

### `get_alarms`

**Purpose:** Active or historical alarms for an asset, site or unit.  
**Description shown to clients:** List alarms filtered by asset, site, unit, status, severity and time range (newest first).  
**Underlying API operation:** `GET /alarms (follows pagination when fetch_all_pages=true, max 5 pages)`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "asset_id": {
      "anyOf": [
        {
          "description": "Asset id, e.g. AST-BFP-101",
          "pattern": "^AST-[A-Z]{3}-\\d{3}$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Asset Id"
    },
    "site": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Site"
    },
    "unit": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Unit"
    },
    "status": {
      "anyOf": [
        {
          "enum": [
            "active",
            "acknowledged",
            "cleared"
          ],
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Status"
    },
    "severity": {
      "anyOf": [
        {
          "items": {
            "enum": [
              "low",
              "medium",
              "high",
              "critical"
            ],
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Severity"
    },
    "start_time": {
      "anyOf": [
        {
          "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
          "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Start Time"
    },
    "end_time": {
      "anyOf": [
        {
          "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
          "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "End Time"
    },
    "page": {
      "default": 1,
      "minimum": 1,
      "title": "Page",
      "type": "integer"
    },
    "page_size": {
      "default": 50,
      "maximum": 200,
      "minimum": 1,
      "title": "Page Size",
      "type": "integer"
    },
    "fetch_all_pages": {
      "default": false,
      "description": "Follow pagination (max 5 pages)",
      "title": "Fetch All Pages",
      "type": "boolean"
    },
    "sort_order": {
      "default": "desc",
      "enum": [
        "asc",
        "desc"
      ],
      "title": "Sort Order",
      "type": "string"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "title": "get_alarmsArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "Alarm": {
      "properties": {
        "alarm_id": {
          "title": "Alarm Id",
          "type": "string"
        },
        "asset_id": {
          "title": "Asset Id",
          "type": "string"
        },
        "asset_name": {
          "title": "Asset Name",
          "type": "string"
        },
        "site": {
          "title": "Site",
          "type": "string"
        },
        "unit": {
          "title": "Unit",
          "type": "string"
        },
        "alarm_name": {
          "title": "Alarm Name",
          "type": "string"
        },
        "alarm_code": {
          "title": "Alarm Code",
          "type": "string"
        },
        "alarm_type": {
          "title": "Alarm Type",
          "type": "string"
        },
        "severity": {
          "title": "Severity",
          "type": "string"
        },
        "status": {
          "title": "Status",
          "type": "string"
        },
        "start_time": {
          "title": "Start Time",
          "type": "string"
        },
        "end_time": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "End Time"
        },
        "ack_time": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ack Time"
        },
        "ack_delay_seconds": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ack Delay Seconds"
        },
        "duration_seconds": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Duration Seconds"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "alarm_id",
        "asset_id",
        "asset_name",
        "site",
        "unit",
        "alarm_name",
        "alarm_code",
        "alarm_type",
        "severity",
        "status",
        "start_time",
        "description"
      ],
      "title": "Alarm",
      "type": "object"
    },
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    },
    "Pagination": {
      "properties": {
        "page": {
          "title": "Page",
          "type": "integer"
        },
        "page_size": {
          "title": "Page Size",
          "type": "integer"
        },
        "total": {
          "title": "Total",
          "type": "integer"
        },
        "total_pages": {
          "title": "Total Pages",
          "type": "integer"
        },
        "has_next": {
          "title": "Has Next",
          "type": "boolean"
        },
        "truncated": {
          "anyOf": [
            {
              "type": "boolean"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Truncated"
        }
      },
      "required": [
        "page",
        "page_size",
        "total",
        "total_pages",
        "has_next"
      ],
      "title": "Pagination",
      "type": "object"
    }
  },
  "properties": {
    "alarms": {
      "items": {
        "$ref": "#/$defs/Alarm"
      },
      "title": "Alarms",
      "type": "array"
    },
    "pagination": {
      "$ref": "#/$defs/Pagination"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "alarms",
    "pagination",
    "meta"
  ],
  "title": "AlarmListResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "get_alarms",
  "arguments": {
    "asset_id": "AST-BFP-101",
    "status": "active",
    "page_size": 2
  }
}
```

**Example response** (long lists shortened)

```json
{
  "alarms": [
    {
      "alarm_id": "ALM-001794",
      "asset_id": "AST-BFP-101",
      "asset_name": "Boiler Feed Pump 101",
      "site": "NorthPlant",
      "unit": "Unit 1",
      "alarm_name": "High Discharge Pressure",
      "alarm_code": "PMP-PH-01",
      "alarm_type": "process",
      "severity": "critical",
      "status": "active",
      "start_time": "2026-10-26T01:47:43Z",
      "end_time": null,
      "ack_time": null,
      "ack_delay_seconds": null,
      "duration_seconds": null,
      "description": "High Discharge Pressure on Boiler Feed Pump 101"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 2,
    "total": 1,
    "total_pages": 1,
    "has_next": false,
    "truncated": null
  },
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 15.4,
    "pages_fetched": null
  }
}
```

### `get_alarm_details`

**Purpose:** One alarm by id.  
**Description shown to clients:** Get one alarm by its id.  
**Underlying API operation:** `GET /alarms/{alarm_id}`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "alarm_id": {
      "description": "Alarm id, e.g. ALM-000123",
      "pattern": "^ALM-\\d{6}$",
      "title": "Alarm Id",
      "type": "string"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "alarm_id"
  ],
  "title": "get_alarm_detailsArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "Alarm": {
      "properties": {
        "alarm_id": {
          "title": "Alarm Id",
          "type": "string"
        },
        "asset_id": {
          "title": "Asset Id",
          "type": "string"
        },
        "asset_name": {
          "title": "Asset Name",
          "type": "string"
        },
        "site": {
          "title": "Site",
          "type": "string"
        },
        "unit": {
          "title": "Unit",
          "type": "string"
        },
        "alarm_name": {
          "title": "Alarm Name",
          "type": "string"
        },
        "alarm_code": {
          "title": "Alarm Code",
          "type": "string"
        },
        "alarm_type": {
          "title": "Alarm Type",
          "type": "string"
        },
        "severity": {
          "title": "Severity",
          "type": "string"
        },
        "status": {
          "title": "Status",
          "type": "string"
        },
        "start_time": {
          "title": "Start Time",
          "type": "string"
        },
        "end_time": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "End Time"
        },
        "ack_time": {
          "anyOf": [
            {
              "type": "string"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ack Time"
        },
        "ack_delay_seconds": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Ack Delay Seconds"
        },
        "duration_seconds": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Duration Seconds"
        },
        "description": {
          "title": "Description",
          "type": "string"
        }
      },
      "required": [
        "alarm_id",
        "asset_id",
        "asset_name",
        "site",
        "unit",
        "alarm_name",
        "alarm_code",
        "alarm_type",
        "severity",
        "status",
        "start_time",
        "description"
      ],
      "title": "Alarm",
      "type": "object"
    },
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    }
  },
  "properties": {
    "alarm": {
      "$ref": "#/$defs/Alarm"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "alarm",
    "meta"
  ],
  "title": "AlarmDetailResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "get_alarm_details",
  "arguments": {
    "alarm_id": "ALM-001794"
  }
}
```

**Example response** (long lists shortened)

```json
{
  "alarm": {
    "alarm_id": "ALM-001794",
    "asset_id": "AST-BFP-101",
    "asset_name": "Boiler Feed Pump 101",
    "site": "NorthPlant",
    "unit": "Unit 1",
    "alarm_name": "High Discharge Pressure",
    "alarm_code": "PMP-PH-01",
    "alarm_type": "process",
    "severity": "critical",
    "status": "active",
    "start_time": "2026-10-26T01:47:43Z",
    "end_time": null,
    "ack_time": null,
    "ack_delay_seconds": null,
    "duration_seconds": null,
    "description": "High Discharge Pressure on Boiler Feed Pump 101"
  },
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 15.3,
    "pages_fetched": null
  }
}
```

### `get_alarm_summary`

**Purpose:** Counts, recurring rate, ack delay grouped by alarm name.  
**Description shown to clients:** Summarise alarms in a time range: counts, recurring rate and ack delay, grouped (e.g. by alarm name).  
**Underlying API operation:** `POST /alarms/summary`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "start_time": {
      "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
      "title": "Start Time",
      "type": "string"
    },
    "end_time": {
      "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
      "title": "End Time",
      "type": "string"
    },
    "asset_ids": {
      "anyOf": [
        {
          "items": {
            "description": "Asset id, e.g. AST-BFP-101",
            "pattern": "^AST-[A-Z]{3}-\\d{3}$",
            "type": "string"
          },
          "maxItems": 20,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Asset Ids"
    },
    "site": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Site"
    },
    "unit": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Unit"
    },
    "severity": {
      "anyOf": [
        {
          "items": {
            "enum": [
              "low",
              "medium",
              "high",
              "critical"
            ],
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Severity"
    },
    "group_by": {
      "default": [
        "alarm_name"
      ],
      "items": {
        "enum": [
          "alarm_name",
          "alarm_code",
          "asset_id",
          "asset_name",
          "severity",
          "alarm_type"
        ],
        "type": "string"
      },
      "title": "Group By",
      "type": "array"
    },
    "kpis": {
      "default": [
        "alarm_count",
        "recurring_rate",
        "avg_ack_delay"
      ],
      "items": {
        "enum": [
          "alarm_count",
          "recurring_rate",
          "avg_ack_delay",
          "critical_count",
          "active_count"
        ],
        "type": "string"
      },
      "title": "Kpis",
      "type": "array"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "start_time",
    "end_time"
  ],
  "title": "get_alarm_summaryArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    }
  },
  "properties": {
    "total_alarms": {
      "title": "Total Alarms",
      "type": "integer"
    },
    "overall": {
      "additionalProperties": true,
      "title": "Overall",
      "type": "object"
    },
    "groups": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Groups",
      "type": "array"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "total_alarms",
    "overall",
    "groups",
    "meta"
  ],
  "title": "AlarmSummaryResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "get_alarm_summary",
  "arguments": {
    "asset_ids": [
      "AST-BFP-101"
    ],
    "start_time": "2026-07-28T00:00:00Z",
    "end_time": "2026-10-26T00:00:00Z",
    "severity": [
      "high",
      "critical"
    ]
  }
}
```

**Example response** (long lists shortened)

```json
{
  "total_alarms": 76,
  "overall": {
    "alarm_count": 76,
    "recurring_rate": 0.145,
    "avg_ack_delay": 624.5
  },
  "groups": [
    {
      "alarm_name": "High Discharge Pressure",
      "alarm_count": 47,
      "recurring_rate": 0.234,
      "avg_ack_delay": 608.7
    },
    {
      "alarm_name": "High Bearing Temperature",
      "alarm_count": 14,
      "recurring_rate": 0.0,
      "avg_ack_delay": 658.9
    },
    {
      "alarm_name": "Low Suction Pressure",
      "alarm_count": 6,
      "recurring_rate": 0.0,
      "avg_ack_delay": 637.7
    },
    "... 2 more item(s) not shown"
  ],
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 16.3,
    "pages_fetched": null
  }
}
```

### `get_alarm_trends`

**Purpose:** Alarm rate per day/week and trend direction.  
**Description shown to clients:** Alarm count per day/week and whether the trend is increasing, decreasing or flat.  
**Underlying API operation:** `POST /alarms/trends`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "start_time": {
      "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
      "title": "Start Time",
      "type": "string"
    },
    "end_time": {
      "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
      "title": "End Time",
      "type": "string"
    },
    "asset_ids": {
      "anyOf": [
        {
          "items": {
            "description": "Asset id, e.g. AST-BFP-101",
            "pattern": "^AST-[A-Z]{3}-\\d{3}$",
            "type": "string"
          },
          "maxItems": 20,
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Asset Ids"
    },
    "site": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Site"
    },
    "unit": {
      "anyOf": [
        {
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Unit"
    },
    "bucket": {
      "default": "weekly",
      "enum": [
        "daily",
        "weekly"
      ],
      "title": "Bucket",
      "type": "string"
    },
    "severity": {
      "anyOf": [
        {
          "items": {
            "enum": [
              "low",
              "medium",
              "high",
              "critical"
            ],
            "type": "string"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Severity"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "start_time",
    "end_time"
  ],
  "title": "get_alarm_trendsArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    }
  },
  "properties": {
    "bucket": {
      "title": "Bucket",
      "type": "string"
    },
    "trend_direction": {
      "title": "Trend Direction",
      "type": "string"
    },
    "series": {
      "items": {
        "additionalProperties": true,
        "type": "object"
      },
      "title": "Series",
      "type": "array"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "bucket",
    "trend_direction",
    "series",
    "meta"
  ],
  "title": "AlarmTrendResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "get_alarm_trends",
  "arguments": {
    "asset_ids": [
      "AST-BFP-101"
    ],
    "start_time": "2026-07-28T00:00:00Z",
    "end_time": "2026-10-26T00:00:00Z",
    "bucket": "weekly"
  }
}
```

**Example response** (long lists shortened)

```json
{
  "bucket": "weekly",
  "trend_direction": "increasing",
  "series": [
    {
      "bucket_start": "2026-07-28T00:00:00Z",
      "alarm_count": 5,
      "critical_count": 2
    },
    {
      "bucket_start": "2026-08-04T00:00:00Z",
      "alarm_count": 8,
      "critical_count": 0
    },
    {
      "bucket_start": "2026-08-11T00:00:00Z",
      "alarm_count": 8,
      "critical_count": 3
    },
    "... 10 more item(s) not shown"
  ],
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 16.3,
    "pages_fetched": null
  }
}
```

### `correlate_alarms`

**Purpose:** Alarms that happen together -> likely causes.  
**Description shown to clients:** Find alarms that repeatedly happen together (on the assets and their related assets).
Helps find likely causes.  
**Underlying API operation:** `POST /alarms/correlation`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "asset_ids": {
      "items": {
        "description": "Asset id, e.g. AST-BFP-101",
        "pattern": "^AST-[A-Z]{3}-\\d{3}$",
        "type": "string"
      },
      "maxItems": 10,
      "minItems": 1,
      "title": "Asset Ids",
      "type": "array"
    },
    "start_time": {
      "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
      "title": "Start Time",
      "type": "string"
    },
    "end_time": {
      "description": "UTC timestamp, e.g. 2026-05-01T00:00:00Z",
      "pattern": "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$",
      "title": "End Time",
      "type": "string"
    },
    "lag_window_minutes": {
      "default": 15,
      "maximum": 120,
      "minimum": 1,
      "title": "Lag Window Minutes",
      "type": "integer"
    },
    "severity_threshold": {
      "default": "medium",
      "enum": [
        "low",
        "medium",
        "high",
        "critical"
      ],
      "title": "Severity Threshold",
      "type": "string"
    },
    "min_support": {
      "default": 2,
      "maximum": 100,
      "minimum": 1,
      "title": "Min Support",
      "type": "integer"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "asset_ids",
    "start_time",
    "end_time"
  ],
  "title": "correlate_alarmsArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "AlarmRef": {
      "properties": {
        "asset_id": {
          "title": "Asset Id",
          "type": "string"
        },
        "asset_name": {
          "title": "Asset Name",
          "type": "string"
        },
        "alarm_name": {
          "title": "Alarm Name",
          "type": "string"
        }
      },
      "required": [
        "asset_id",
        "asset_name",
        "alarm_name"
      ],
      "title": "AlarmRef",
      "type": "object"
    },
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    },
    "CorrelatedPair": {
      "properties": {
        "leading_alarm": {
          "$ref": "#/$defs/AlarmRef"
        },
        "following_alarm": {
          "$ref": "#/$defs/AlarmRef"
        },
        "support": {
          "title": "Support",
          "type": "integer"
        },
        "confidence": {
          "title": "Confidence",
          "type": "number"
        },
        "avg_lag_minutes": {
          "title": "Avg Lag Minutes",
          "type": "number"
        }
      },
      "required": [
        "leading_alarm",
        "following_alarm",
        "support",
        "confidence",
        "avg_lag_minutes"
      ],
      "title": "CorrelatedPair",
      "type": "object"
    }
  },
  "properties": {
    "assets_in_scope": {
      "items": {
        "type": "string"
      },
      "title": "Assets In Scope",
      "type": "array"
    },
    "events_analyzed": {
      "title": "Events Analyzed",
      "type": "integer"
    },
    "correlated_pairs": {
      "items": {
        "$ref": "#/$defs/CorrelatedPair"
      },
      "title": "Correlated Pairs",
      "type": "array"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "assets_in_scope",
    "events_analyzed",
    "correlated_pairs",
    "meta"
  ],
  "title": "CorrelationResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "correlate_alarms",
  "arguments": {
    "asset_ids": [
      "AST-BFP-101"
    ],
    "start_time": "2026-07-28T00:00:00Z",
    "end_time": "2026-10-26T00:00:00Z",
    "min_support": 5
  }
}
```

**Example response** (long lists shortened)

```json
{
  "assets_in_scope": [
    "AST-BFP-101",
    "AST-DEA-101",
    "AST-FCV-101",
    "... 1 more item(s) not shown"
  ],
  "events_analyzed": 186,
  "correlated_pairs": [
    {
      "leading_alarm": {
        "asset_id": "AST-FCV-101",
        "asset_name": "Feedwater Control Valve FCV-101",
        "alarm_name": "Valve Position Deviation"
      },
      "following_alarm": {
        "asset_id": "AST-BFP-101",
        "asset_name": "Boiler Feed Pump 101",
        "alarm_name": "High Discharge Pressure"
      },
      "support": 30,
      "confidence": 0.75,
      "avg_lag_minutes": 3.0
    },
    {
      "leading_alarm": {
        "asset_id": "AST-BFP-101",
        "asset_name": "Boiler Feed Pump 101",
        "alarm_name": "High Discharge Pressure"
      },
      "following_alarm": {
        "asset_id": "AST-MTR-101",
        "asset_name": "BFP Motor 101",
        "alarm_name": "High Winding Temperature"
      },
      "support": 16,
      "confidence": 0.296,
      "avg_lag_minutes": 6.3
    },
    {
      "leading_alarm": {
        "asset_id": "AST-FCV-101",
        "asset_name": "Feedwater Control Valve FCV-101",
        "alarm_name": "Valve Position Deviation"
      },
      "following_alarm": {
        "asset_id": "AST-MTR-101",
        "asset_name": "BFP Motor 101",
        "alarm_name": "High Winding Temperature"
      },
      "support": 15,
      "confidence": 0.375,
      "avg_lag_minutes": 9.0
    },
    "... 3 more item(s) not shown"
  ],
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 17.5,
    "pages_fetched": null
  }
}
```

### `score_alarm_priority`

**Purpose:** 0-100 priority with explanation.  
**Description shown to clients:** Score how urgent an alarm is (0-100, P1-P4) and explain the factors.  
**Underlying API operation:** `POST /alarms/priority-score`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "alarm_id": {
      "description": "Alarm id, e.g. ALM-000123",
      "pattern": "^ALM-\\d{6}$",
      "title": "Alarm Id",
      "type": "string"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "alarm_id"
  ],
  "title": "score_alarm_priorityArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    },
    "PriorityFactor": {
      "properties": {
        "factor": {
          "title": "Factor",
          "type": "string"
        },
        "value": {
          "title": "Value"
        },
        "points": {
          "title": "Points",
          "type": "integer"
        }
      },
      "required": [
        "factor",
        "value",
        "points"
      ],
      "title": "PriorityFactor",
      "type": "object"
    }
  },
  "properties": {
    "alarm_id": {
      "title": "Alarm Id",
      "type": "string"
    },
    "priority_score": {
      "title": "Priority Score",
      "type": "integer"
    },
    "priority_level": {
      "title": "Priority Level",
      "type": "string"
    },
    "factors": {
      "items": {
        "$ref": "#/$defs/PriorityFactor"
      },
      "title": "Factors",
      "type": "array"
    },
    "explanation": {
      "title": "Explanation",
      "type": "string"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "alarm_id",
    "priority_score",
    "priority_level",
    "factors",
    "explanation",
    "meta"
  ],
  "title": "PriorityScoreResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "score_alarm_priority",
  "arguments": {
    "alarm_id": "ALM-001794"
  }
}
```

**Example response** (long lists shortened)

```json
{
  "alarm_id": "ALM-001794",
  "priority_score": 87,
  "priority_level": "P1",
  "factors": [
    {
      "factor": "severity",
      "value": "critical",
      "points": 40
    },
    {
      "factor": "asset_criticality",
      "value": "high",
      "points": 20
    },
    {
      "factor": "recurrence_30d",
      "value": 17,
      "points": 17
    },
    "... 2 more item(s) not shown"
  ],
  "explanation": "High Discharge Pressure on Boiler Feed Pump 101 scored 87/100 (P1). Main drivers: severity=critical, asset_criticality=high.",
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 15.3,
    "pages_fetched": null
  }
}
```

### `get_operator_recommendations`

**Purpose:** API recommended actions + related assets.  
**Description shown to clients:** Get the API's recommended operator actions for an alarm plus related assets to check.  
**Underlying API operation:** `POST /recommendations/operator-actions`  
**Auth / errors / timeout:** see shared behaviour above.

<details><summary>Input schema</summary>

```json
{
  "properties": {
    "alarm_id": {
      "description": "Alarm id, e.g. ALM-000123",
      "pattern": "^ALM-\\d{6}$",
      "title": "Alarm Id",
      "type": "string"
    },
    "include_related": {
      "default": true,
      "title": "Include Related",
      "type": "boolean"
    },
    "include_asset_context": {
      "default": true,
      "title": "Include Asset Context",
      "type": "boolean"
    },
    "include_historical_pattern": {
      "default": true,
      "title": "Include Historical Pattern",
      "type": "boolean"
    },
    "trace_id": {
      "anyOf": [
        {
          "maxLength": 64,
          "type": "string"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "description": "Optional correlation id, forwarded to the API",
      "title": "Trace Id"
    }
  },
  "required": [
    "alarm_id"
  ],
  "title": "get_operator_recommendationsArguments",
  "type": "object"
}
```
</details>

<details><summary>Output schema</summary>

```json
{
  "$defs": {
    "CallMeta": {
      "description": "How the underlying API call went (shown in the GUI trace).",
      "properties": {
        "trace_id": {
          "title": "Trace Id",
          "type": "string"
        },
        "status_code": {
          "title": "Status Code",
          "type": "integer"
        },
        "attempts": {
          "description": "1 = first try worked, >1 = retries happened",
          "title": "Attempts",
          "type": "integer"
        },
        "duration_ms": {
          "title": "Duration Ms",
          "type": "number"
        },
        "pages_fetched": {
          "anyOf": [
            {
              "type": "integer"
            },
            {
              "type": "null"
            }
          ],
          "default": null,
          "title": "Pages Fetched"
        }
      },
      "required": [
        "trace_id",
        "status_code",
        "attempts",
        "duration_ms"
      ],
      "title": "CallMeta",
      "type": "object"
    },
    "RecommendedAction": {
      "properties": {
        "step": {
          "title": "Step",
          "type": "integer"
        },
        "action": {
          "title": "Action",
          "type": "string"
        },
        "urgency": {
          "title": "Urgency",
          "type": "string"
        },
        "source": {
          "title": "Source",
          "type": "string"
        }
      },
      "required": [
        "step",
        "action",
        "urgency",
        "source"
      ],
      "title": "RecommendedAction",
      "type": "object"
    }
  },
  "properties": {
    "alarm_id": {
      "title": "Alarm Id",
      "type": "string"
    },
    "alarm_name": {
      "title": "Alarm Name",
      "type": "string"
    },
    "asset_id": {
      "title": "Asset Id",
      "type": "string"
    },
    "asset_name": {
      "title": "Asset Name",
      "type": "string"
    },
    "severity": {
      "title": "Severity",
      "type": "string"
    },
    "recommended_actions": {
      "items": {
        "$ref": "#/$defs/RecommendedAction"
      },
      "title": "Recommended Actions",
      "type": "array"
    },
    "related_assets_to_check": {
      "anyOf": [
        {
          "items": {
            "additionalProperties": true,
            "type": "object"
          },
          "type": "array"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Related Assets To Check"
    },
    "asset_context": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Asset Context"
    },
    "historical_pattern": {
      "anyOf": [
        {
          "additionalProperties": true,
          "type": "object"
        },
        {
          "type": "null"
        }
      ],
      "default": null,
      "title": "Historical Pattern"
    },
    "meta": {
      "$ref": "#/$defs/CallMeta"
    }
  },
  "required": [
    "alarm_id",
    "alarm_name",
    "asset_id",
    "asset_name",
    "severity",
    "recommended_actions",
    "meta"
  ],
  "title": "OperatorRecommendationResult",
  "type": "object"
}
```
</details>

**Example invocation**

```json
{
  "tool": "get_operator_recommendations",
  "arguments": {
    "alarm_id": "ALM-001794"
  }
}
```

**Example response** (long lists shortened)

```json
{
  "alarm_id": "ALM-001794",
  "alarm_name": "High Discharge Pressure",
  "asset_id": "AST-BFP-101",
  "asset_name": "Boiler Feed Pump 101",
  "severity": "critical",
  "recommended_actions": [
    {
      "step": 1,
      "action": "Check the position of the downstream control valve and confirm it is not closing unexpectedly",
      "urgency": "immediate",
      "source": "alarm_api_rule_engine"
    },
    {
      "step": 2,
      "action": "Verify discharge pressure on the local gauge to rule out a faulty transmitter",
      "urgency": "immediate",
      "source": "alarm_api_rule_engine"
    },
    {
      "step": 3,
      "action": "Reduce load or open the recirculation (minimum flow) line to bring pressure below the limit",
      "urgency": "immediate",
      "source": "alarm_api_rule_engine"
    },
    "... 1 more item(s) not shown"
  ],
  "related_assets_to_check": [
    {
      "asset_id": "AST-MTR-101",
      "asset_name": "BFP Motor 101",
      "relationship": "driven_by"
    },
    {
      "asset_id": "AST-FCV-101",
      "asset_name": "Feedwater Control Valve FCV-101",
      "relationship": "downstream_valve"
    },
    {
      "asset_id": "AST-DEA-101",
      "asset_name": "Deaerator Tank D-101",
      "relationship": "suction_source"
    }
  ],
  "asset_context": {
    "asset_type": "pump",
    "criticality": "high",
    "last_maintenance_date": "2026-02-18",
    "operating_limits": {
      "discharge_pressure_bar": 120,
      "bearing_temp_c": 85,
      "vibration_mm_s": 7.1
    }
  },
  "historical_pattern": {
    "occurrences_total": 120,
    "most_common_hours_utc": [
      11,
      15,
      18
    ],
    "first_seen": "2026-04-01T13:00:00Z",
    "last_seen": "2026-10-26T01:47:43Z"
  },
  "meta": {
    "trace_id": "catalog",
    "status_code": 200,
    "attempts": 1,
    "duration_ms": 16.2,
    "pages_fetched": null
  }
}
```
