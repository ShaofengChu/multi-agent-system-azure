import os
import uuid
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from agent import process_hr_task

app = FastAPI(title="HR Agent")

AGENT_URL = os.environ.get("AGENT_URL", "http://quizzical_kepler:8000/hr-agent")


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
        "name": "HR Agent",
        "description": "HR関連業務の処理：従業員情報の照会、入社プロセス",
        "url": AGENT_URL,
        "preferredTransport": "JSONRPC",
        "version": "1.0.0",
        "capabilities": {"streaming": False, "pushNotifications": False},
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": "query_employee",
                "name": "従業員情報の照会",
                "description": "従業員IDに基づいて基本情報を取得する",
                "tags": ["query", "employee", "hr"],
            },
            {
                "id": "onboard_employee",
                "name": "従業員入社",
                "description": "新入社員の入社手続きを行う",
                "tags": ["onboard", "employee", "hr"],
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
    result = await process_hr_task(user_text)

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
    return {"status": "ok", "agent": "hr-agent"}
