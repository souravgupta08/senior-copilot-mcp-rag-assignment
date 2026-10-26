#!/usr/bin/env bash
# Starts the simulator and the copilot locally (the copilot starts the MCP server over stdio itself).
# Usage: bash scripts/run_local.sh     then open http://127.0.0.1:8080
set -e
python -m rag.ingestion.ingest
uvicorn apps.alarm_simulator.main:app --port 8000 &
SIM_PID=$!
trap "kill $SIM_PID" EXIT
sleep 2
uvicorn apps.backend.app:app --port 8080
