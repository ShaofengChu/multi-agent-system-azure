from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import uuid
import os
import jwt
from jwt import PyJWKClient
from agent import process_hr_task

app = FastAPI()

# --- OAuth 2.0 認証設定の追加 ---
# 環境変数からAzure Entra IDの設定を取得する
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID", "あなたの_Tenant_ID")
# これはEntra IDでAPIを公開した際に設定したアプリケーションID URI (Audience)
AZURE_AUDIENCE = os.environ.get("AZURE_AUDIENCE", "api://あなたの_HR_Agent_Client_ID")

# Entra IDの公開鍵を取得するためのJWKSエンドポイント
jwks_url = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/discovery/v2.0/keys"
jwks_client = PyJWKClient(jwks_url)
security = HTTPBearer()

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """送信されたBearerトークンを検証する"""
    token = credentials.credentials
    try:
        # 現在のトークンを署名するために使用された公開鍵を取得する
        signing_key = jwks_client.get_signing_key_from_jwt(token)
        
        # トークンの検証: 署名、Audience、有効期限のチェック
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=AZURE_AUDIENCE,
            options={"verify_issuer": False} # A2A通信では通常、署名とAudienceを信頼すればよい
        )
        
        # App Rolesを設定した場合、特定のRoleが含まれているかをさらに確認する
        roles = payload.get("roles", [])
        if "Agent.Invoke" not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="権限が不十分です。「Agent.Invoke」ロールがありません。",
            )
            
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="トークンの有効期限が切れています")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"無効なトークンです: {str(e)}")
# --- 認証設定ここまで ---

# Agent Card
@app.get("/.well-known/agent-card.json")
async def agent_card():
    return {
        "protocolVersion": "0.3.0",
        "name": "HR Agent",
        "description": "HR関連業務の処理：従業員情報の照会、入社プロセス",
        "url": "https://hr-agent.mangobeach-77bfed4b.japaneast.azurecontainerapps.io/",
        "preferredTransport": "JSONRPC",
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "capabilities": {"streaming": False, "pushNotifications": False},
        "provider": {"organization":"chu","url":"https://chu.com"},
        # --- 修正: OAuth2セキュリティスキームを宣言 ---
        "securitySchemes": {
            "entra_id_oauth2": {
                "type": "oauth2",
                "flows": {
                    "clientCredentials": {
                        "tokenUrl": f"https://login.microsoftonline.com/{AZURE_TENANT_ID}/oauth2/v2.0/token",
                        "scopes": {
                            f"{AZURE_AUDIENCE}/.default": "Access HR Agent API"
                        }
                    }
                }
            }
        },
        "supportsAuthenticatedExtendedCard":False,
        "version": "1.0.0",
        "skills": [
            {
                "id": "query_employee",
                "name": "従業員情報の照会",
                "description": "従業員IDに基づいて基本情報を取得する",
                "tags": ["query", "employee", "hr"]
            },
            {
                "id": "onboard_employee",
                "name": "従業員入社",
                "description": "新入社員の入社手続きを行う",
                "tags": ["onboard", "employee", "hr"]
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
# --- 追加: Depends(verify_token)で認証を必須にする ---
@app.post("/tasks/send", dependencies=[Depends(verify_token)])
async def handle_task(req: JsonRpcRequest):
    req_id = req.id
    
    # JSON-RPCの params.message からテキストを取得
    user_text = req.params.message.parts[0]["text"]
    
    # タスク自体のIDはエージェント側で新規発行
    task_id = str(uuid.uuid4())
    
    result = await process_hr_task(user_text)
    
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
    return {"status": "ok", "agent": "hr-agent"}

# --- ルートエンドポイントを追加 ---
# --- 追加: Depends(verify_token)で認証を必須にする ---
@app.post("/", dependencies=[Depends(verify_token)])
async def handle_root(req: JsonRpcRequest):
    return await handle_task(req)