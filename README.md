# マルチエージェントシステム (Azure)

本リポジトリは、**Azure OpenAI** と **Model Context Protocol (MCP)** を使用したマルチエージェントオーケストレーションシステムの実装です。特化したエージェントが集中型ツールサーバーと連携し、従業員データの取得やIT機器の管理などのビジネスオペレーションを実行する方法を示します。

本バージョンでは、システム全体の安全性を高めるため、エージェント間通信（A2A: Agent-to-Agent）に **Azure Entra ID を用いた OAuth 2.0 クライアント資格情報フロー（Client Credentials Flow）** による認証機能を追加しています。これにより、HRエージェント、ITエージェント、Salesforceエージェント、およびMCPサーバーの構築、構成、セキュアな運用が可能となります。

## アーキテクチャ

システムは、**Azure Container Apps** 上にデプロイされる複数のコンポーネントで構成されています。

1. **MCP ツールサーバー (`/mcp_server`)**: データ取得や状態変更（例: ノートPCの割り当て）のためのツールを公開する `FastMCP` サーバー。
2. **HR エージェント (`/hr_agent`)**: Azure OpenAI を搭載した特化型エージェント。従業員情報やオンボーディングに焦点を当てています。ハードウェアに関するタスクはITに委任するよう指示されています。
3. **IT エージェント (`/it_agent`)**: Azure OpenAI を搭載した特化型エージェント。機器の管理と割り当てに焦点を当てています。
4. **Salesforce エージェント (`/salesforce_agent`)**: Salesforceデータ等と連携するための特化型エージェント。

```text
[クライアント] --JSON-RPC/A2A--> [各エージェント (FastAPI)] --MCP/streamable-http--> [MCP サーバー (FastMCP)]
                                    |
                            [Azure OpenAI API]
```

## 主な機能

* **ツールの分離**: データアクセスのロジックは MCP サーバーで一元処理されるため、さまざまなエージェント間で再利用可能です。
* **ネイティブ JSON Schema**: Azure OpenAI はツール定義として標準の JSON Schema を受け入れるため、スキーマの変換は必要ありません。
* **自律的なツール実行**: エージェントは複雑なクエリを解決するために、自律的にツールをループ内で呼び出すことができます（最大5回のイテレーション）。
* **ペルソナベースのルーティング**: システムプロンプト（指示）により、エージェントは自身の機能ドメイン内に留まることが保証されます。
* **A2A プロトコル**: 相互運用性のために、エージェントは Google の Agent-to-Agent プロトコルのエンドポイントを公開しています。
* **OAuth 2.0 認証**: Azure Entra ID を利用し、エージェント間通信のセキュリティを強固に保護します。

## 前提条件１：Azure OpenAI リソースの作成とキーの取得


各エージェントが大規模言語モデル（LLM）を利用できるようにするため、事前に Azure OpenAI Service の設定を行います。

### ステップ 1: Azure OpenAI リソースの作成
1. [Azure ポータル](https://portal.azure.com/) にログインします。
2. 上部の検索バーに「**Azure OpenAI**」と入力し、サービスを選択します。
3. 「**作成**」をクリックし、以下の項目を入力・選択します：
   - **サブスクリプション**: 利用可能なサブスクリプションを選択。
   - **リソースグループ**: 既存のグループを選択、または新規作成。
   - **リージョン**: 利用可能なリージョン（例: `East US`, `Japan East` など）を選択。
   - **名前**: リソースの一意の名前（例: `my-openai-resource`）。
   - **価格層**: `S0` を選択。
4. 「確認と作成」をクリックし、検証が成功したら「**作成**」をクリックしてデプロイを完了させます。

### ステップ 2: モデルのデプロイ（Deployment Name の取得）
1. 作成した Azure OpenAI リソースの「概要」画面から、「**Azure OpenAI Studio**」に移動します。
2. 左側メニューの「**デプロイ (Deployments)**」を選択し、「**新しいデプロイの作成**」をクリックします。
3. 使用するモデル（例: `gpt-4o-mini` または `gpt-35-turbo`）を選択します。
4. **重要:** 「**デプロイ名 (Deployment name)**」を入力します。ここで設定した文字列（例: `gpt-4o-mini-deploy`）は、環境変数の `AZURE_OPENAI_DEPLOYMENT_NAME` に正確に設定する必要があります（※ベースモデル名とは異なる場合があります）。

### ステップ 3: API キーとエンドポイントの取得
1. Azure ポータルの Azure OpenAI リソース画面に戻り、左側メニューの「**リソース管理**」 > 「**キーとエンドポイント (Keys and Endpoint)**」をクリックします。
2. 表示される「**キー 1 (KEY 1)**」（API Key）と「**エンドポイント (Endpoint)**」をコピーして安全に保管します。



## 前提条件２：Azure Entra ID OAuth 2.0 の設定手順

エージェント間のバックエンド通信（不特定多数のユーザーが介在しないサービス間通信）を保護するため、Azure Entra ID で2つのアプリケーション（リソース側とクライアント側）を登録します。

### 1) リソースアプリケーションの登録（例：IT-Agent-API）

1. Azure ポータルで **Microsoft Entra ID** に移動し、「**アプリの登録 (App registrations)**」 > 「**新規登録**」をクリックします。
2. 名前（例: `IT-Agent-API`）を入力し、サポートされているアカウントの種類を「この組織ディレクトリ内のアカウントのみ」にして「**登録**」をクリックします。
3. **API の公開 (Expose an API)**: 左メニューの「API の公開」をクリックし、「アプリケーション ID URI」の「**追加**」をクリックして保存します。
4. **アプリロール (App Roles) の作成**:
* 左メニューの「アプリロール」から「**アプリロールの作成**」をクリックします。
* 表示名: `Agent.Invoke`
* 許可されたメンバーの種類: **アプリケーション (Applications)** （※サービス間通信に必須）
* 値: `Agent.Invoke`
* 「適用」をクリックして保存します。


5. **重要: マニフェスト (Manifest) の修正（v2.0 トークンの強制）**:
* 左メニューの「**マニフェスト (Manifest)**」をクリックします。
* JSON エディター内で `"accessTokenAcceptedVersion"` を探し、値を `null` から `2` に変更して保存します。
* これにより、標準的な v2.0 JWT トークンが発行され、暗号化パディングエラーを回避できます。
* **注意:** v2.0 トークンでは、トークン内の `aud` (Audience) 属性が `api://<Client-ID>` ではなく、純粋なアプリケーションの「クライアント ID (UUID)」になります。



### 2) クライアントアプリケーションの登録（例：MuleSoft Broker / 呼び出し側 Agent）

1. 再び「**アプリの登録**」から、呼び出し側を表すアプリ（例: `Agent-Client`）を新規登録します。
2. 概要画面に表示される「**アプリケーション (クライアント) ID**」をコピーします。
3. **クライアントシークレットの生成**:
* 左メニューの「**証明書とシークレット**」から「**新しいクライアントシークレット**」を追加し、生成されたシークレットの「**値 (Value)**」を控えます。


4. **API のアクセス許可の付与**:
* 左メニューの「**API のアクセス許可**」から「**アクセス許可の追加**」をクリックします。
* 「**自分の API (My APIs)**」タブに切り替え、先ほど作成した `IT-Agent-API` を選択します。
* 「**アプリケーションの許可 (Application permissions)**」を選択し、`Agent.Invoke` にチェックを入れて追加します。
* 最後に「**＜組織名＞ に管理者の同意を与えます (Grant admin consent)**」をクリックし、ステータスを緑色にします。



## 環境変数（.env）の設定

リポジトリのルートディレクトリに `.env` ファイルを作成し、取得した各種資格情報を設定します。

```env
# --- Azure OpenAI 設定 ---
AZURE_OPENAI_ENDPOINT="https://<あなたのリソース名>[.openai.azure.com/](https://.openai.azure.com/)"
AZURE_OPENAI_API_KEY="your-api-key-here"
AZURE_OPENAI_DEPLOYMENT_NAME="<Azure OpenAI Studioで設定した正確なデプロイ名>"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"

# --- MCP サーバー設定 ---
MCP_SERVER_URL="http://localhost:8003/mcp"
PORT=8080

# --- Azure Entra ID 認証設定 ---
AZURE_TENANT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# 各エージェントのリソースアプリの「クライアント ID (UUID)」を指定します
# (マニフェストでv2.0を有効にしているため、api:// プレフィックスは不要です)
AZURE_AUDIENCE_IT="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
AZURE_AUDIENCE_HR="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
AZURE_AUDIENCE_SF="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

## コードレイヤーにおける認証仕様の説明

各エージェント（FastAPI）の内部では、`PyJWT` と `cryptography` を使用して、受信した HTTP Bearer トークンの安全性を検証しています。

1. **JWKSエンドポイントの利用**: FastAPI 起動時、Microsoft のメタデータエンドポイントから Entra ID が署名に使用した最新の公開鍵セット（JWKS）を自動的に取得します。
2. **署名と有効期限の自動検証**: リクエストの `Authorization` ヘッダーから抽出されたJWTに対し、公開鍵を用いて署名、有効期限（`exp`）、および受取人（`aud`）のチェックを非同期かつ厳密に行います。
3. **ロールベースの認可 (RBAC)**: トークンのクレームから `roles` 配列を抽出し、事前定義された `Agent.Invoke` ロールが含まれているか検証します。不足している場合は `403 Forbidden` を返します。

## 実行とテスト手順

### ローカル開発 (Docker Compose)

1. 上記の手順に従い、プロジェクトのルートディレクトリに `.env` ファイルを作成します。
2. 全てのサービスを起動します:
```bash
docker-compose up --build
```



### Postman を使用した認証機能のテスト

MuleSoft などのクライアント側を結合する前に、Postman を使用して単体で認証フローのテストを行うことができます。

#### ステップ 1: Azure Entra ID から Access Token を取得する

1. Postman で新規リクエストを作成（メソッド: `POST` / URL: `https://login.microsoftonline.com/<あなたの_TENANT_ID>/oauth2/v2.0/token`）
2. **Body** タブで **`x-www-form-urlencoded`** を選択し、以下を入力:
* `grant_type`: `client_credentials`
* `client_id`: `<クライアントアプリ(Agent-Client)の クライアント ID>`
* `client_secret`: `<生成したクライアントシークレットの値>`
* `scope`: `<リソースアプリのクライアントID>/.default`


3. 送信し、返された JSON の `"access_token"` の値をコピーします。

#### ステップ 2: トークンを使用して Agent API を呼び出す

1. 新規リクエストを作成（メソッド: `POST` / URL: `http://localhost:8082/tasks/send` ※ITエージェントの例）
2. **Headers** タブで追加:
* Key: `Authorization`
* Value: `Bearer <コピーした access_token>`


3. **Body** タブで **`raw`** 形式（`JSON`）を選択し、リクエストを入力:
```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "id": "test01",
  "params": {
    "message": {
      "role": "user",
      "parts": [
        {"text":"現在利用可能なノートパソコンを教えてください。"}
      ]
    }
  }
}
```


4. 送信して `200 OK` が返ることを確認します。トークンがない場合は `401 Unauthorized` または `403 Forbidden` となります。

### クラウドデプロイ (Azure Container Apps)

1. Azure CLI がログイン済みであることを確認します:
```bash
az login
```


2. 必要な環境変数をエクスポートします（CI/CDやシェル上で設定）。
3. デプロイ用スクリプトを実行します:
```bash
bash deploy.sh
```


*これにより、ACRの作成、Dockerイメージのビルドとプッシュ、各エージェントおよびMCPサーバーのデプロイが自動で行われます。*
4. デプロイ完了後、ターミナルに出力されたURLを用いて、各エージェントの URL 設定を更新してください。

## プロジェクト構成

```text
multi-agent-system-azure/
├── deploy.sh          # Azure Container Apps へのデプロイ用スクリプト
├── docker-compose.yml # Docker Compose を使用したローカル開発環境
├── hr_agent/          # HR エージェント
│   ├── agent.py       # Azure OpenAI + MCP ツール呼び出しループ
│   └── main.py        # A2A プロトコルエンドポイントを持つ FastAPI サーバー
├── it_agent/          # IT エージェント
│   ├── agent.py       
│   └── main.py        
├── salesforce_agent/  # Salesforce エージェント
│   ├── agent.py       
│   └── main.py        
└── mcp_server/        # MCP サーバー
    ├── main.py        # FastMCP サーバー定義とツールロジック
    └── data.py        # 従業員やノートPCのモックデータベース
```

## 利用可能なツール

MCP サーバーを介して以下のツールが利用可能です:

* `get_employee_info`: 従業員の名前、部署、雇用日を取得します。
* `get_available_laptops`: ステータスが「available (利用可能)」なハードウェアをリストアップします。
* `assign_equipment`: 特定のノートPCを従業員 ID に紐付けて割り当てます。