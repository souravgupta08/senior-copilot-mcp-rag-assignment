# One image for all three Python services (simulator, MCP server, copilot).
# docker-compose.yml decides which command each container runs.
FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY . .

# Build the RAG index at image build time (it is plain JSON, rebuilt on every build)
RUN python -m rag.ingestion.ingest

# Run as a non-root user
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8000 8080 9000

CMD ["uvicorn", "apps.backend.app:app", "--host", "0.0.0.0", "--port", "8080"]
