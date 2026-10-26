# Handy shortcuts. On Windows run the commands inside each target directly.
PY ?= python

install:
	$(PY) -m pip install -r requirements-dev.txt

ingest:
	$(PY) -m rag.ingestion.ingest

simulator:
	uvicorn apps.alarm_simulator.main:app --port 8000

mcp-server:
	$(PY) mcp-servers/alarm-management/alarm_mcp_server.py

mcp-server-http:
	MCP_TRANSPORT=streamable-http $(PY) mcp-servers/alarm-management/alarm_mcp_server.py

copilot:
	uvicorn apps.backend.app:app --port 8080

test:
	$(PY) -m pytest -q

coverage:
	$(PY) -m pytest -q --cov --cov-report=term --cov-report=html:htmlcov --cov-report=xml:coverage.xml

lint:
	ruff check . && ruff format --check .

format:
	ruff format . && ruff check --fix .

postman:
	bash scripts/run_postman.sh

up:
	docker compose up --build

down:
	docker compose down

.PHONY: install ingest simulator mcp-server mcp-server-http copilot test coverage lint format postman up down
