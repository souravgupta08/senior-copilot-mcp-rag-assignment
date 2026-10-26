#!/usr/bin/env bash
# Demo helper: makes the simulator fail on purpose so you can show retries / partial failure in the GUI.
# Usage:
#   bash scripts/demo_failure.sh correlation   -> /alarms/correlation always returns 503
#   bash scripts/demo_failure.sh flaky         -> 30% of all calls fail (retries will often recover)
#   bash scripts/demo_failure.sh reset         -> back to normal
BASE_URL=${ALARM_API_BASE_URL:-http://localhost:8000}
TOKEN=${ALARM_API_TOKEN:-demo-token}
case "$1" in
  correlation) BODY='{"fail_paths": ["/alarms/correlation"]}' ;;
  flaky)       BODY='{"failure_rate": 0.3}' ;;
  *)           BODY='{}' ;;
esac
curl -s -X POST "$BASE_URL/admin/chaos" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "$BODY"
echo
