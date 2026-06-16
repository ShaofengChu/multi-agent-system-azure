# マルチエージェントシステム (Azure) - 開発・運用ガイド

本リポジトリは、Azure環境で動作するマルチエージェントシステム（HRエージェント、ITエージェント、Salesforceエージェント、およびMCPサーバー）の構築、構成、およびセキュアな運用を行うためのガイドラインです。

本バージョンでは、システム全体の安全性を高めるため、エージェント間通信（A2A: Agent-to-Agent）に **Azure Entra ID を用いた OAuth 2.0 クライアント資格情報フロー（Client Credentials Flow）** による認証機能を追加しています。

---

## 目次
1. [前提条件: Azure OpenAI リソースの作成とキーの取得](#1-前提条件-azure-openai-リソースの作成とキーの取得)
2. [Azure Entra ID OAuth 2.0 の設定手順](#2-azure-entra-id-oauth-20-の設定手順)
3. [環境変数（.env）の設定](#3-環境変数envの設定)
4. [コードレイヤーにおける認証仕様の説明](#4-コードレイヤーにおける認証仕様の説明)
5. [Postman を使用した認証機能のテスト手順](#5-postman-を使用した認証機能のテスト手順)
6. [ローカル環境での実行方法](#6-ローカル環境での実行方法)

---

## 1. 前提条件: Azure OpenAI リソースの作成とキーの取得

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

---

## 2. Azure Entra ID OAuth 2.0 の設定手順

エージェント間のバックエンド通信（不特定多数のユーザーが介在しないサービス間通信）を保護するため、Azure Entra ID で2つのアプリケーション（リソース側とクライアント側）を登録します。

### 1) リソースアプリケーションの登録（例：IT-Agent-API）
1. Azure ポータルで **Microsoft Entra ID** に移動し、「**アプリの登録 (App registrations)**」 > 「**新規登録**」をクリックします。
2. 名前（例: `IT-Agent-API`）を入力し、サポートされているアカウントの種類を「この組織ディレクトリ内のアカウントのみ」にして「**登録**」をクリックします。
3. **API の公開 (Expose an API)**:
   - 左メニューの「API の公開」をクリックし、「アプリケーション ID URI」の「**追加**」をクリックして保存します（デフォルトは `api://<Client-ID>`）。
4. **アプリロール (App Roles) の作成**:
   - 左メニューの「アプリロール」をクリックし、「**アプリロールの作成**」をクリックします。
   - 表示名: `Agent.Invoke`
   - 許可されたメンバーの種類: **アプリケーション (Applications)** （※サービス間通信に必須）
   - 値: `Agent.Invoke`
   - 「適用」をクリックして保存します。
5. **重要: マニフェスト (Manifest) の修正（v2.0 トークンの強制）**:
   - 左メニューの「**マニフェスト (Manifest)**」をクリックします。
   - JSON エディター内で `"accessTokenAcceptedVersion"` を探し、値を `null` から `2` に変更します。
   - 頂部の「**保存**」をクリックします。これにより、Python の `PyJWT` ライブラリと完全な互換性を持つ標準的な v2.0 JWT トークンが発行されるようになり、暗号化パディングエラー（`Invalid crypto padding`）を回避できます。
   - **注意:** v2.0 トークンでは、トークン内の `aud` (Audience) 属性が `api://<Client-ID>` ではなく、**純粋なアプリケーションの「クライアント ID (UUID)」**になります。

### 2) クライアントアプリケーションの登録（例：MuleSoft Broker / 调用側 Agent）
1. 再び「**アプリの登録**」 > 「**新規登録**」から、呼び出し側を表すアプリ（例: `Agent-Client`）を登録します。
2. 概要画面に表示される「**アプリケーション (クライアント) ID**」をコピーします。
3. **クライアントシークレットの生成**:
   - 左メニューの「**証明書とシークレット**」 > 「**新しいクライアントシークレット**」をクリックします。
   - 説明を入力して有効期限を選択し、「追加」をクリックします。
   - 生成されたシークレットの「**値 (Value)**」をすぐにコピーして控えます（画面を離れると二度と表示されません）。
4. **API のアクセス許可の付与**:
   - 左メニューの「**API のアクセス許可**」 > 「**アクセス許可の追加**」をクリックします。
   - 「**自分の API (My APIs)**」タブに切り替え、先ほど作成した `IT-Agent-API` を選択します。
   - 「**アプリケーションの許可 (Application permissions)**」を選択し、`Agent.Invoke` にチェックを入れて「アクセス許可の追加」をクリックします。
   - 権限一覧の画面で、「**＜組織名＞ に管理者の同意を与えます (Grant admin consent)**」をクリックし、ステータスが緑色のチェック（付与済み）になったことを確認します。

---

## 3. 環境変数（.env）の設定

リポジトリのルートディレクトリに `.env` ファイルを作成し、取得した各種資格情報を設定します。

```env
# --- Azure OpenAI 設定 ---
AZURE_OPENAI_ENDPOINT="https://<あなたのリソース名>[.openai.azure.com/](https://.openai.azure.com/)"
AZURE_OPENAI_API_KEY="xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
AZURE_OPENAI_DEPLOYMENT_NAME="<Azure OpenAI Studioで設定した正確なデプロイ名>"
AZURE_OPENAI_API_VERSION="2024-02-15-preview"

# --- Azure Entra ID 認証設定 ---
AZURE_TENANT_ID="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

# 各エージェントのリソースアプリの「クライアント ID (UUID)」を指定します
# (マニフェストでv2.0を有効にしているため、api:// プレフィックスは不要です)
AZURE_AUDIENCE_IT="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
AZURE_AUDIENCE_HR="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
AZURE_AUDIENCE_SF="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

```

---

## 4. コードレイヤーにおける認証仕様の説明

各エージェント（FastAPI）の内部では、`PyJWT` と `cryptography` を使用して、受信した HTTP Bearer トークンの安全性を検証しています。

### 検証ロジックのフロー

1. **JWKSエンドポイントの利用**:
FastAPI 起動時、Microsoft のメタデータエンドポイント (`https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys`) から、Entra ID が署名に使用した最新の公開鍵セット（JWKS）を自動的に取得します。
2. **署名と有効期限の自動検証**:
リクエストの `Authorization` ヘッダーから抽出されたJWTに対し、公開鍵を用いて署名チェック、有効期限（`exp`）チェック、および受取人（`aud`）のチェックを非同期かつ厳密に行います。
3. **ロールベースの認可 (RBAC)**:
トークンのクレームから `roles` 配列を抽出し、事前定義された `Agent.Invoke` ロールが含まれているか検証します。不足している場合は `403 Forbidden` を返します。

この検証ロジックは、タスク処理エンドポイント（`/tasks/send` やルート `/`）の FastAPI 依存関係（`Depends(verify_token)`）としてグローバルに適用されています。

---

## 5. Postman を使用した認証機能のテスト手順

MuleSoft などのクライアント側を結合する前に、Postman を使用して単体で認証フローのテストを行うことができます。

### ステップ 1: Azure Entra ID から Access Token を取得する

1. Postman で新しいリクエストを作成します。
* **メソッド**: `POST`
* **URL**: `https://login.microsoftonline.com/<あなたの_TENANT_ID>/oauth2/v2.0/token`


2. **Body** タブに移動し、**`x-www-form-urlencoded`** を選択して以下のキーと値を入力します：
* `grant_type`: `client_credentials`
* `client_id`: `<クライアントアプリ(Agent-Client)の クライアント ID>`
* `client_secret`: `<生成したクライアントシークレットの値>`
* `scope`: `<リソースアプリのクライアントID>/.default` （例: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx/.default`）


3. 「**Send**」をクリックします。成功すると JSON レスポンスが返され、その中の `"access_token"` の値（非常に長い文字列）をコピーします。

### ステップ 2: トークンを使用して Agent API を呼び出す

1. 新しいリクエストを作成します。
* **メソッド**: `POST`
* **URL**: `http://localhost:8082/tasks/send` (ITエージェントのローカルポート例)


2. **Headers** タブに移動し、以下のヘッダーを追加します：
* **Key**: `Authorization`
* **Value**: `Bearer <コピーした access_token>` （※Bearerとトークンの間には半角スペースが1つ必要です）


3. **Body** タブに移動し、**`raw`** を選択、フォーマットを **`JSON`** に設定して JSON-RPC 2.0 形式のリクエストを入力します：
```json
{
    "jsonrpc": "2.0",
    "method": "tasks.send",
    "id": "test-session-001",
    "params": {
        "message": {
            "role": "user",
            "parts": [{"kind": "text", "text": "新しいMacBookの在庫を確認してください"}]
        }
    }
}

```


4. 「**Send**」をクリックします。
* 認証および設定が正常な場合: `200 OK` とともに、エージェントが処理した成功レスポンスが返されます。
* トークンを付与しない、あるいは偽装した場合: `401 Unauthorized` または `403 Forbidden` が返されることを確認してください。
