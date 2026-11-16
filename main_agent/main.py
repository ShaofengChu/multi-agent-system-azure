from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent import discover_agents, process_main_task


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Discover subagent Agent Cards on startup."""
    await discover_agents()
    yield


app = FastAPI(title="Main Orchestrator Agent", lifespan=lifespan)


class ChatRequest(BaseModel):
    message: str | None = None
    query: str | None = None


@app.post("/chat")
async def chat(req: ChatRequest) -> dict[str, Any]:
    """Accept a user query and orchestrate subagents via A2A."""
    user_text = (req.message or req.query or "").strip()
    if not user_text:
        raise HTTPException(
            status_code=400,
            detail="リクエストボディに空でない 'message' または 'query' を指定してください。",
        )

    result = await process_main_task(user_text)
    return {"response": result}


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "agent": "main-agent"}
