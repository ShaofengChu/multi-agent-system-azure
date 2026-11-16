# マルチエージェントシステム (Azure / A2A Orchestration)

本リポジトリは、**Azure OpenAI**、**標準 A2A (Agent2Agent) プロトコル**、および **Model Context Protocol (MCP)** を組み合わせたマルチエージェントオーケストレーションシステムの実装です。

オーケストレーターである `main_agent` が各特化型サブエージェント（`hr_agent`、`it_agent`、`salesforce_agent`）の Agent Card（`/.well-known/agent.json`）を動的に取得し、OpenAI Tool Calling を通じて標準 A2A JSON-RPC 2.0（`POST /a2a`, `method: "tasks/send"`）でタスクを委譲・集約します。

セキュリティ面では、OAuth 2.0 認証に代わり **ネットワーク分離構成** を採用しており、外部公開（External Ingress）されるのは `main_agent` のみで、サブエージェントおよび MCP サーバーは内部ネットワーク（Internal Ingress）からのみアクセス可能です。

## アーキテクチャ

システムは、Docker Compose（ローカル）および **Azure Container Apps**（クラウド）上にデプロイされる以下の 5 つのコンポーネントで構成されています。

1. **Main エージェント (`/main_agent`)** — **External Ingress (Port 8000)**:
   * 外部クライアント向けの唯一のエントリーポイント（`POST /chat`, `GET /health`）。
   * 起動時（および未取得時のリクエスト処理時）に各サブエージェントの `GET /.well-known/agent.json` を取得し、OpenAI Function Calling 用のツール（`call_hr_agent`, `call_it_agent`, `call_salesforce_agent`）を動的に登録します。
   * OpenAI Tool Calling でルーティング先を判断し、対象サブエージェントの `POST /a2a` へ JSON-RPC 2.0 (`tasks/send`) リクエストを非同期送信して最終回答を生成します。
2. **HR エージェント (`/hr_agent`)** — **Internal Only (Port 8080)**:
   * 従業員情報の照会や入社関連業務を担当する A2A 対応サブエージェント。
3. **IT エージェント (`/it_agent`)** — **Internal Only (Port 8080)**:
   * ノート PC などの IT 機器の在庫照会と割り当てを担当する A2A 対応サブエージェント。
4. **Salesforce エージェント (`/salesforce_agent`)** — **Internal Only (Port 8080)**:
   * Salesforce のカスタムタスク情報の照会を担当する A2A 対応サブエージェント。
5. **MCP ツールサーバー (`/mcp_server`)** — **Internal Only (Port 8080)**:
   * 従業員情報・IT 機器データの取得や状態変更（ノート PC の割り当てなど）を提供する `FastMCP` サーバー。

```text
[外部クライアント]
        |  HTTP POST /chat (External: Port 8000 / ACA External Ingress)
        v
+-------------------------------------------------------------------+
|  main_agent (オーケストレーター / OpenAI Tool Calling + A2A Client) |
+-------------------------------------------------------------------+
        |   内部ネットワーク限定 (agent_internal_net / ACA Internal Ingress)
        |   1. GET /.well-known/agent.json (動的ディスカバリ)
        |   2. POST /a2a (JSON-RPC 2.0 method: "tasks/send")
        +-------------------+-------------------+
        |                   |                   |
        v                   v                   v
  [hr_agent]           [it_agent]      [salesforce_agent]
        |                   |                   |
        +---------+---------+                   |
                  | MCP (streamable-http)       | MCP (streamable-http)
                  v                             v
            [mcp_server]               [Salesforce MCP Server]
```

## 主な機能

* **標準 A2A プロトコル準拠**: 各サブエージェントは `GET /.well-known/agent.json`（Agent Card）および `POST /a2a`（JSON-RPC 2.0 `tasks/send`）を公開しています。
* **動的サービスディスカバリ & Tool 登録**: `main_agent` がサブエージェントのスキル情報を `/.well-known/agent.json` から自動取得し、OpenAI の `tools` 定義を動的に構築します。
* **マルチエージェント並列オーケストレーション**: 単一または複数ドメインにまたがる問い合わせを LLM が分解し、複数のサブエージェントへ並列で A2A タスクを送信・集約できます。
* **ネットワーク分離**: ローカル（Docker Compose の `agent_internal_net` + `expose`）とクラウド（ACA `--ingress internal`）の双方で、サブサービスへの直接の外部アクセスを遮断しています。
* **ツールの分離 (MCP)**: ビジネスデータ操作は MCP サーバーに集約され、各エージェントから再利用可能です。

## 前提条件：Azure OpenAI リソースの作成とキーの取得

各エージェントが大規模言語モデル（LLM）を利用できるようにするため、事前に Azure OpenAI Service の設定を行います。

### ステップ 1: Azure OpenAI リソースの作成
1. [Azure ポータル](https://portal.azure.com/) にログインします。
2. 上部の検索バーに「**Azure OpenAI**」と入力し、サービスを選択します。
3. 「**作成**」をクリックし、サブスクリプション・リソースグループ・リージョン・名前・価格層（`S0`）を設定して作成します。

### ステップ 2: モデルのデプロイ（Deployment Name の取得）
1. 作成した Azure OpenAI リソースから **Azure AI Foundry / Azure OpenAI Studio** に移動します。
2. 「**デプロイ (Deployments)**」から使用するモデル（例: `gpt-5-mini`, `gpt-4o-mini` など）をデプロイし、設定した「**デプロイ名 (Deployment name)**」を控えます。

### ステップ 3: API キーとエンドポイントの取得
1. Azure OpenAI リソースの「**キーとエンドポイント (Keys and Endpoint)**」から **キー 1** と **エンドポイント** をコピーします。

## 環境変数（.env）の設定

リポジトリのルートディレクトリに `.env` ファイルを作成し、Azure OpenAI の接続情報を設定します（OAuth 2.0 / Entra ID 関連の変数は不要です）。

```env
# --- Azure OpenAI 設定 ---
AZURE_OPENAI_ENDPOINT="https://<あなたのリソース名>.openai.azure.com/"
AZURE_OPENAI_API_KEY="your-api-key-here"
AZURE_OPENAI_DEPLOYMENT_NAME="<Azure OpenAIで設定したデプロイ名>"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"

# --- Salesforce MCP サーバー設定（任意） ---
# SALESFORCE_MCP_SERVER_URL="https://mulesoft-generative-ai-mcp-server-4aa6a9.zlqs1p.jpn-e1.cloudhub.io/mcp"
```

## 実行とテスト手順

### ローカル開発 (Docker Compose)

1. リポジトリのルートディレクトリに上記の `.env` ファイルを作成します。
2. 全サービスをビルド・起動します:
   ```bash
   docker-compose up --build
   ```
   * `main-agent` のみが `localhost:8000` に公開されます。
   * `hr-agent`、`it-agent`、`salesforce-agent`、`mcp-server` は内部ネットワーク `agent_internal_net` 内の `8080` 番ポート（`expose`）でのみ通信可能です。

3. ヘルスチェックを確認します:
   ```bash
   curl http://localhost:8000/health
   ```

4. `POST /chat` でオーケストレーターへ問い合わせを送信します:
   ```bash
   # IT エージェントのみを利用する例
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "現在利用可能なノートパソコンを教えてください。"}'

   # HR エージェントと IT エージェントを連携させる例
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "従業員 E002 の情報を確認し、利用可能なノートパソコンを1台割り当ててください。"}'

   # Salesforce エージェントを利用する例
   curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Salesforce のタスク一覧を取得して整理してください。"}'
   ```

### クラウドデプロイ (Azure Container Apps)

1. Azure CLI でログイン済みであることを確認します:
   ```bash
   az login
   ```

2. 必要な環境変数をシェルに設定します:
   ```bash
   export AZURE_OPENAI_ENDPOINT="https://<あなたのリソース名>.openai.azure.com/"
   export AZURE_OPENAI_API_KEY="your-api-key-here"
   export AZURE_OPENAI_DEPLOYMENT_NAME="<デプロイ名>"
   export AZURE_OPENAI_API_VERSION="2024-12-01-preview"
   ```

3. デプロイスクリプトを実行します:
   ```bash
   bash deploy.sh
   ```
   スクリプトは以下を自動的に実行します:
   * Azure Container Registry (ACR) と Container Apps Environment (`multi-agent-env`) の作成（既存利用可）
   * 5 つのイメージ（`mcp-server`, `hr-agent`, `it-agent`, `salesforce-agent`, `main-agent`）の ACR ビルド & プッシュ
   * `mcp-server`, `hr-agent`, `it-agent`, `salesforce-agent` を `--ingress internal --target-port 8080` でデプロイ
   * `main-agent` を `--ingress external --target-port 8000` でデプロイし、内部通信 URL（`http://hr-agent`, `http://it-agent`, `http://salesforce-agent`）を環境変数として注入

4. デプロイ完了後に出力された `https://<MAIN_FQDN>/chat` に対してリクエストを送信して動作確認を行います:
   ```bash
   curl -X POST "https://<MAIN_FQDN>/chat" \
     -H "Content-Type: application/json" \
     -d '{"message": "従業員 E001 の情報と利用可能なノートPCを教えてください。"}'
   ```

## プロジェクト構成

```text
multi-agent-system-azure/
├── deploy.sh              # Azure Container Apps デプロイスクリプト (External/Internal Ingress 分離)
├── docker-compose.yml     # Docker Compose ローカル開発環境 (agent_internal_net)
├── README.md
├── main_agent/            # メインオーケストレーター (External: 8000)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── agent.py           # /.well-known/agent.json 動的取得 & OpenAI Tool Calling + A2A 呼び出し
│   └── main.py            # POST /chat, GET /health を公開する FastAPI サーバー
├── hr_agent/              # HR サブエージェント (Internal: 8080)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── agent.py           # Azure OpenAI + MCP ツール呼び出しループ
│   └── main.py            # GET /.well-known/agent.json, POST /a2a, GET /health
├── it_agent/              # IT サブエージェント (Internal: 8080)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── agent.py
│   └── main.py            # GET /.well-known/agent.json, POST /a2a, GET /health
├── salesforce_agent/      # Salesforce サブエージェント (Internal: 8080)
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── agent.py
│   └── main.py            # GET /.well-known/agent.json, POST /a2a, GET /health
└── mcp_server/            # MCP サーバー (Internal: 8080)
    ├── Dockerfile
    ├── requirements.txt
    ├── main.py            # FastMCP サーバー定義とツールロジック
    └── data.py            # 従業員やノートPCのモックデータベース
```

## 利用可能なツール (MCP Server)

`mcp_server` を介して以下のツールが利用可能です:

* `get_employee_info`: 従業員の名前、部署、入社日を取得します。
* `get_available_laptops`: ステータスが `available` なノートパソコンをリストアップします。
* `assign_equipment`: 指定されたノートパソコンを従業員 ID に紐付けて割り当てます。
