import os
import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from agent import process_it_task

app = FastAPI(title="IT Agent")

AGENT_URL = os.environ.get("AGENT_URL", "http://kong-gateway:8000/it-agent")


class Message(BaseModel):
    role: str = "user"
    parts: list[dict[str, Any]]


class SendMessageParams(BaseModel):
    id: str | None = None
    message: Message


class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    id: str | int | None = None
    params: SendMessageParams


def _extract_user_text(parts: list[dict[str, Any]]) -> str:
    """Extract concatenated text content from A2A message parts."""
    texts = [
        part["text"]
        for part in parts
        if isinstance(part, dict) and isinstance(part.get("text"), str) and part["text"].strip()
    ]
    return "\n".join(texts).strip()


@app.get("/.well-known/agent.json")
@app.get("/.well-known/agent-card.json")
async def agent_card() -> dict[str, Any]:
    """Return the standard A2A Agent Card describing this agent's capabilities."""
    return {
        "protocolVersion": "0.3.0",
        "name": "IT Agent",
        "description": "IT機器関連業務の処理：機器の照会と割り当て",
        "url": AGENT_URL,
        "preferredTransport": "JSONRPC",
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "query_equipment",
                "name": "機器照会",
                "description": "利用可能な機器を照会する",
                "tags": ["query", "equipment"],
            },
            {
                "id": "assign_equipment",
                "name": "機器割り当て",
                "description": "従業員に機器を割り当てる",
                "tags": ["assign", "equipment"],
            },
        ],
    }


@app.post("/a2a")
@app.post("/tasks/send")
@app.post("/")
async def handle_task(req: JsonRpcRequest) -> dict[str, Any]:
    """Handle A2A JSON-RPC 2.0 task execution requests."""
    if req.method not in ("tasks/send", "message/send"):
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "error": {"code": -32601, "message": f"Method not found: {req.method}"},
        }

    user_text = _extract_user_text(req.params.message.parts)
    if not user_text:
        return {
            "jsonrpc": "2.0",
            "id": req.id,
            "error": {"code": -32602, "message": "Invalid params: message parts must contain text"},
        }

    task_id = req.params.id or str(uuid.uuid4())
    context_id = str(req.id) if req.id is not None else task_id
    result = await process_it_task(user_text)

    return {
        "jsonrpc": "2.0",
        "id": req.id,
        "result": {
            "id": task_id,
            "contextId": context_id,
            "kind": "task",
            "status": {
                "state": "completed",
                "message": {
                    "role": "agent",
                    "parts": [{"type": "text", "text": result}],
                },
            },
            "artifacts": [
                {
                    "artifactId": str(uuid.uuid4()),
                    "parts": [{"type": "text", "text": result, "kind": "text"}],
                }
            ],
        },
    }


@app.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok", "agent": "it-agent"}
