"""Copilot API + GUI.

uvicorn apps.backend.app:app --port 8080
"""

import json
import logging
import time
import traceback
import uuid
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from apps.backend.mcp_client import list_server_tools
from apps.backend.workflow import get_retriever, run_copilot

FRONTEND_DIR = Path(__file__).resolve().parents[1] / "frontend"

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("copilot")

app = FastAPI(
    title="Alarm Investigation Copilot",
    description="Alarm investigation and procedure guidance using MCP tools + document RAG",
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(FRONTEND_DIR / "templates"))


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    thread_id: str | None = Field(default=None, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html", context={})


@app.post("/api/chat")
async def chat(body: ChatRequest):
    request_id = f"req-{uuid.uuid4().hex[:10]}"
    message = body.message.strip()
    if not message:
        return JSONResponse(status_code=400, content={"success": False, "error": "Message cannot be empty."})

    started = time.perf_counter()
    try:
        result = await run_copilot(message, body.thread_id)
    except Exception as error:
        traceback.print_exc()
        logger.error(
            json.dumps(
                {"service": "copilot", "request_id": request_id, "outcome": "error", "error": type(error).__name__}
            )
        )
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "request_id": request_id,
                "error": "The copilot failed to answer. Check the server logs.",
            },
        )

    # One structured log line per request (no secrets, no full documents)
    logger.info(
        json.dumps(
            {
                "service": "copilot",
                "request_id": request_id,
                "conversation_id": result["thread_id"],
                "trace_id": result["trace_id"],
                "intent": result["intent"],
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "tools": [
                    {
                        "tool": s["tool"],
                        "status": s.get("status"),
                        "ms": s.get("duration_ms"),
                        "attempts": s.get("attempts"),
                    }
                    for s in result["trace"]
                ],
                "retrieval_query": (result["retrieval"] or {}).get("query"),
                "retrieved": [{"chunk": c["chunk_id"], "score": c["score"]} for c in result["citations"]],
                "answer_source": result["answer_source"],
            }
        )
    )
    return {"success": True, "request_id": request_id, **result}


@app.get("/api/tools")
async def tools():
    """Tool discovery view: everything the MCP server offers, with schemas."""
    try:
        return {"success": True, "tools": await list_server_tools()}
    except Exception as error:
        return JSONResponse(
            status_code=503, content={"success": False, "error": f"MCP server unavailable: {type(error).__name__}"}
        )


@app.get("/api/documents")
async def documents():
    retriever = get_retriever()
    return {"built_at": retriever.built_at, "documents": retriever.documents, "chunks": len(retriever.chunks)}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "alarm-investigation-copilot"}


if __name__ == "__main__":
    uvicorn.run("apps.backend.app:app", host="127.0.0.1", port=8080, reload=False)
