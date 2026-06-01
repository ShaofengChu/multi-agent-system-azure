from fastapi import FastAPI
from pydantic import BaseModel
import uuid
from agent import process_salesforce_task

app = FastAPI()

# Agent Card
@app.get("/.well-known/agent-card.json")
async def agent_card():
    return {
        "protocolVersion": "0.3.0",
        "name": "Salesforce Agent",
        "description": "Salesforceタスク管理：タスク情報の取得と照会",
        "url": "https://salesforce-agent.mangobeach-77bfed4b.japaneast.azurecontainerapps.io/",
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
                "id": "get_sf_task",
                "name": "Salesforceタスク取得",
                "description": "Salesforceからタスク情報を取得する",
                "tags": ["query", "salesforce", "task"]
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
    
    result = await process_salesforce_task(user_text)
    
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
    return {"status": "ok", "agent": "salesforce-agent"}

# --- ルートエンドポイントを追加 ---
@app.post("/")
async def handle_root(req: JsonRpcRequest):
    return await handle_task(req)
