from fastapi import FastAPI
from pydantic import BaseModel
import uuid
from agent import process_it_task

app = FastAPI()

# Agent Card
@app.get("/.well-known/agent-card.json")
async def agent_card():
    return {
        "protocolVersion": "0.3.0",
        "name": "IT Agent",
        "description": "IT機器関連業務の処理：機器の照会と割り当て",
        "url": "https://it-agent.<CONTAINER_APPS_ENV>.japaneast.azurecontainerapps.io/",
        "preferredTransport": "JSONRPC",
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "capabilities": {"streaming": False, "pushNotifications": False},
        "provider": {"organization":"chu","url":"https://chu.com"},
        "securitySchemes":{},
        "supportsAuthenticatedExtendedCard":False,
        "version": "1.0.0",
        "skills": [
            {
                "id": "query_equipment",
                "name": "機器照会",
                "description": "利用可能な機器を照会する",
                "tags": ["query", "equipment"]
            },
            {
                "id": "assign_equipment",
                "name": "機器割り当て",
                "description": "従業員に機器を割り当てる",
                "tags": ["assign", "equipment"]
            }
        ]
    }

# タスクエンドポイント
class Message(BaseModel):
    role: str
    parts: list

class SendMessageParams(BaseModel):
    message: Message

class JsonRpcRequest(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    id: str  # Brokerとの通信セッションID
    params: SendMessageParams

# --- 修正: エンドポイントでJSON-RPC Success Responseを返す ---
@app.post("/tasks/send")
async def handle_task(req: JsonRpcRequest):
    req_id = req.id
    
    # JSON-RPCの params.message からテキストを取得
    user_text = req.params.message.parts[0]["text"]
    
    # タスク自体のIDはエージェント側で新規発行
    task_id = str(uuid.uuid4())
    
    result = await process_it_task(user_text)
    
    # A2A SendMessageResponse のフォーマットで返却
    return {
        "jsonrpc": "2.0",
        "id": req_id,
        "result": {
            "kind": "task",
            "id": task_id,
            "contextId": req_id,
            "status": {"state": "completed"},
            "artifacts": [{
                "artifactId": str(uuid.uuid4()),
                "parts": [{"kind": "text", "text": result}]
            }]
        }
    }

@app.get("/health")
async def health():
    return {"status": "ok", "agent": "it-agent"}

# --- ルートエンドポイントを追加 ---
@app.post("/")
async def handle_root(req: JsonRpcRequest):
    return await handle_task(req)