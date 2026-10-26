#!/usr/bin/env bash
# Runs all Postman collections against a running simulator with newman (Postman's CLI).
# Install once: npm install -g newman
# Usage: bash scripts/run_postman.sh [base_url]
set -e
BASE_URL=${1:-http://localhost:8000}
mkdir -p docs/test-evidence
for collection in postman/*.postman_collection.json; do
  name=$(basename "$collection" .postman_collection.json)
  echo "=== $name ==="
  newman run "$collection" --env-var "baseUrl=$BASE_URL" \
    --reporters cli,junit --reporter-junit-export "docs/test-evidence/newman-$name.xml"
done
