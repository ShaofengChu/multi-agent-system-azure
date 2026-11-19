# 構築手順書（2 フェーズ構成：Phase 1 Kong / Phase 2 Agent & MCP）

本ドキュメントでは、以下の **2 フェーズ構成** で Kong AI Gateway（新規 Control Plane + Self-Managed Data Plane）とマルチエージェントシステムを構築し、すべての LLM・A2A・MCP トラフィックを Kong 経由でテストする詳細手順を説明します。

```text
[フェーズ 1: Kong]
  0. 共有 Docker ネットワーク (agent_internal_net) を事前作成
  1. Konnect UI または kongctl で新規 Control Plane を作成
  2. Self-Managed (Docker) の docker run スクリプトを取得し、
     --name kong-gateway --network agent_internal_net を追加して起動
  3. kongctl apply -f kong-ai-gateway/ai-gateway.yaml で LLM / Agent / MCP を登録

[フェーズ 2: Agent / MCP]
  4. docker compose up -d --build で 4 コンテナを起動（agent_internal_net へ自動参加）
  5. Postman / curl で E2E テストを実施し、docker logs kong-gateway で 4 経路を確認
```

---

## 1. Docker 名・ネットワーク固定化に関する設計ポイント

### Q. Kong Data Plane の Docker 名は固定ですか？
**はい、固定名（`kong-gateway`）で起動してください。**

- 各エージェントのコード・環境変数および `docker-compose.yml` は、Docker 内部 DNS 上の固定名 **`kong-gateway`**（`http://kong-gateway:8000`）を参照します。
- **別名を使いたい場合**: `docker run --name <任意の名前>` に合わせて、`.env` の `KONG_GATEWAY_URL=http://<任意の名前>:8000` を変更してください。

### なぜ最初に `docker network create agent_internal_net` して `docker run` に渡すのか
1. **Kong の DNS キャッシュ問題の回避**:  
   デフォルトの `bridge` ネットワークで `docker run` した後に `docker network connect` で後付け接続すると、Kong が起動時に読み込んだ `/etc/resolv.conf` をキャッシュしているため Docker 組み込み DNS（`127.0.0.11`）を参照できず、`503 name resolution failed` になります（回避には `docker restart` が必要）。  
   最初から `--network agent_internal_net` を指定して `docker run` すれば、初回起動時から `hr-agent` / `it-agent` / `main-agent` / `mcp-server` を名前解決できます。
2. **Compose との連携 (`external: true`)**:  
   `docker-compose.yml` の `networks.agent_internal_net` は `external: true` に設定してあるため、フェーズ 2 で `docker compose up -d --build` を実行すると、フェーズ 1 で起動済みの `kong-gateway` と同じ `agent_internal_net` に 4 コンテナがそのまま参加します。

---

## 2. 前提条件

- **Docker**: Docker Desktop または Docker Engine + Docker Compose v2
- **`kongctl` CLI**: v1.28.4 以上（確認: `kongctl version`）
- **Kong Konnect アカウント**: 新規 Control Plane 作成および PAT 発行（または `kongctl login`）が可能な権限
  - 利用リージョンが US（デフォルト）以外の場合は、`--region eu` 等または環境変数 `KONGCTL_DEFAULT_KONNECT_REGION` を指定してください。
- **Azure OpenAI リソース情報**: リソース名（`<INSTANCE>.openai.azure.com` の `<INSTANCE>`）、API キー、デプロイ名、API バージョン

---

## 3. 事前準備（リポジトリ取得・`.env` 作成・共有ネットワーク作成）

### 3-1. リポジトリ取得と `.env` 作成

**Windows (PowerShell):**
```powershell
git clone <リポジトリURL>
cd multi-agent-system-azure
Copy-Item .env.example .env
```

**macOS / Linux (Bash):**
```bash
git clone <リポジトリURL>
cd multi-agent-system-azure
cp .env.example .env
```

`.env` を開き、環境に合わせて値を設定します：

```env
# Azure OpenAI
AZURE_OPENAI_INSTANCE="<your-azure-openai-instance>"
AZURE_OPENAI_API_KEY="<your-azure-openai-api-key>"
AZURE_OPENAI_DEPLOYMENT_NAME="gpt-5-mini"
AZURE_OPENAI_API_VERSION="2024-12-01-preview"

# Kong Konnect / kongctl（フェーズ 1-1 で作成する Control Plane 名に合わせる）
KONNECT_CONTROL_PLANE_NAME="local-poc-ai-gateway-pc2"
# `kongctl login` を使わない場合は PAT を設定
# KONGCTL_DEFAULT_KONNECT_PAT="<your-konnect-pat>"

# Docker Compose（通常は変更不要）
KONG_GATEWAY_URL="http://kong-gateway:8000"
MAIN_AGENT_PORT="8008"
```

> [!NOTE]
> リポジトリ内の `kong-ai-gateway/setting.txt` は旧検証環境時の作業メモ（PAT・秘密鍵を含む）です。別環境へ持ち込む際や Git 管理下では再利用せず、必ず新規 Control Plane と新しい PAT・証明書を使用してください。

### 3-2. 共有 Docker ネットワークの作成

```bash
docker network create agent_internal_net
```

作成確認:
```bash
docker network ls --filter name=agent_internal_net
```

---

## 4. フェーズ 1：Kong（Control Plane 作成 ➔ Data Plane 起動 ➔ `kongctl apply`）

### 1-1. 新規 Control Plane の作成（Konnect UI または `kongctl`）

#### 方法 A: Konnect UI から作成（推奨）
1. Kong Konnect にログインし、**AI Gateway**（Gateway Manager / AI Gateway）を開きます。
2. 新規 AI Gateway Control Plane を作成します（**Deployment Type: Hybrid / Self-Managed**）。
3. 名前は `.env` の `KONNECT_CONTROL_PLANE_NAME` と完全一致させてください（例: `local-poc-ai-gateway-pc2`。小文字英数字とハイフン推奨）。

#### 方法 B: `kongctl` から作成する場合
1. `.env` をシェルに読み込み（手順 1-3-1 参照）、認証を済ませた状態で以下を実行します：
   **Windows (PowerShell):**
   ```powershell
   @"
   _defaults:
     kongctl:
       namespace: kong-control-plane

   ai_gateways:
     - ref: new-ai-gateway
       name: $env:KONNECT_CONTROL_PLANE_NAME
       display_name: $env:KONNECT_CONTROL_PLANE_NAME
       deployment_type: hybrid
       min_runtime_version: "2.3"
       runtime_auto_upgrade: true
   "@ | kongctl apply -f - --auto-approve -o text
   ```
   **macOS / Linux (Bash):**
   ```bash
   cat <<EOF | kongctl apply -f - --auto-approve -o text
   _defaults:
     kongctl:
       namespace: kong-control-plane

   ai_gateways:
     - ref: new-ai-gateway
       name: ${KONNECT_CONTROL_PLANE_NAME}
       display_name: ${KONNECT_CONTROL_PLANE_NAME}
       deployment_type: hybrid
       min_runtime_version: "2.3"
       runtime_auto_upgrade: true
   EOF
   ```
2. 作成後、Konnect UI で該当 Control Plane を開き、次の Data Plane 起動スクリプトを取得します。

---

### 1-2. Self-Managed Data Plane の `docker run` スクリプト取得・固定名で起動

1. Konnect UI で作成した Control Plane を開き、**Data Plane Nodes** ➔ **New Data Plane Node** ➔ **Self-Managed**（Docker / Linux 等）を選択します。
2. 画面に表示される `docker run` スクリプト（mTLS 証明書 `KONG_CLUSTER_CERT` / `KONG_CLUSTER_CERT_KEY` や `KONG_CLUSTER_CONTROL_PLANE` 等が含まれたコマンド）をコピーします。
3. **重要**: 取得したコマンドの先頭 `docker run -d` の直後に、必ず **`--name kong-gateway --network agent_internal_net`** を追加して実行します（ポート `-p 8000:8000` と `-p 8443:8443` が含まれていることも確認してください）。

**修正イメージ（Windows PowerShell の場合）:**
```powershell
docker run -d `
  --name kong-gateway `
  --network agent_internal_net `
  -e "KONG_ROLE=data_plane" `
  ...（Konnect UI で取得した環境変数・ポート設定をそのまま記述）...
  -p 8000:8000 `
  -p 8443:8443 `
  kong/kong-ai-gateway:2.3.0-distroless
```

**修正イメージ（macOS / Linux Bash の場合）:**
```bash
docker run -d \
  --name kong-gateway \
  --network agent_internal_net \
  -e "KONG_ROLE=data_plane" \
  ...（Konnect UI で取得した環境変数・ポート設定をそのまま記述）...
  -p 8000:8000 \
  -p 8443:8443 \
  kong/kong-ai-gateway:2.3.0-distroless
```

4. 起動・ネットワーク参加・Konnect 接続を確認します：
   ```bash
   docker ps --filter name=kong-gateway
   docker inspect kong-gateway --format "{{json .NetworkSettings.Networks}}"
   ```
   `agent_internal_net` に接続されていれば OK です。

---

### 1-3. `kong-ai-gateway/ai-gateway.yaml` を `kongctl apply`

#### 1-3-1. `.env` を現在のシェルに読み込む

**Windows (PowerShell):**
```powershell
Get-Content .env | ForEach-Object {
  if ($_ -match '^\s*([^#=]+?)\s*=\s*"?([^"]*)"?\s*$') {
    [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
  }
}
```

**macOS / Linux (Bash):**
```bash
set -a
. ./.env
set +a
```

#### 1-3-2. `kongctl` 認証確認

`KONGCTL_DEFAULT_KONNECT_PAT` を設定していない場合は `kongctl login` を実行します。その後、以下で認証先オーガニゼーションを確認してください。

```bash
kongctl get organization -o json
```

> [!NOTE]
> Windows 環境で `open ...\kongctl\logs\kongctl.log: Access is denied` が出た場合は、`mkdir .artifacts` して `--log-file .artifacts/kongctl.log` を指定してください。

#### 1-3-3. `kongctl diff` で差分確認 & `kongctl apply` で適用

`kong-ai-gateway/ai-gateway.yaml` は `_external.selector.matchFields.name: !env KONNECT_CONTROL_PLANE_NAME` により、フェーズ 1-1 で作成した Control Plane を名前で自動参照し、その配下に 6 エンティティ（Model Provider / Model / 3 Agents / MCP Server）を登録します。

```bash
# 事前プレビュー（6 to add, 0 to change, 1 secret write を確認）
kongctl diff -f kong-ai-gateway/ai-gateway.yaml --mode apply

# 適用実行
kongctl apply -f kong-ai-gateway/ai-gateway.yaml --auto-approve -o text
```

> [!IMPORTANT]
> 同一 Konnect 組織で複数環境を管理している場合、他のネームスペースのリソースを削除しないよう `sync` ではなく必ず **`apply`**（および `--mode apply`）を使用してください。

---

### 1-4. フェーズ 1 完了確認（ノード同期 & LLM 単体疎通）

1. Data Plane ノードが `STATE_IN_SYNC` になっていることを確認します：
   **PowerShell:**
   ```powershell
   kongctl get ai-gateway nodes --gateway-name $env:KONNECT_CONTROL_PLANE_NAME -o yaml
   ```
   **Bash:**
   ```bash
   kongctl get ai-gateway nodes --gateway-name "$KONNECT_CONTROL_PLANE_NAME" -o yaml
   ```
2. Kong 経由での Azure OpenAI 単体呼び出しを確認します（`model` は `.env` の `AZURE_OPENAI_DEPLOYMENT_NAME` に合わせる）：
   ```bash
   curl -i -X POST http://localhost:8000/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"model":"gpt-5-mini","messages":[{"role":"user","content":"ping"}]}'
   ```
   `HTTP/1.1 200 OK` および応答メッセージが返ればフェーズ 1 は完了です。

---

## 5. フェーズ 2：Agent / MCP（Docker Compose 起動・テスト）

### 2-1. Agent / MCP コンテナのビルド・起動

```bash
docker compose up -d --build
```

起動状態とネットワーク参加状況を確認します：
```bash
docker compose ps
docker network inspect agent_internal_net --format "{{json .Containers}}"
```
`kong-gateway` に加えて `mcp-server`、`hr-agent`、`it-agent`、`main-agent` の計 5 コンテナがすべて `agent_internal_net` 上にあれば準備完了です。

---

### 2-2. Agent Card & ヘルスチェック確認

```bash
# Main Agent ヘルスチェック（Kong 経由）
curl -s -i http://localhost:8000/main-agent/health

# HR / IT Agent Card の取得（Kong type: a2a による url 書き換えも確認）
curl -s http://localhost:8000/hr-agent/.well-known/agent.json
curl -s http://localhost:8000/it-agent/.well-known/agent.json
```

また、コンテナ内部向けの Agent Card `url` が Kong 経由になっていることも確認できます：
```bash
docker compose exec hr-agent python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/.well-known/agent.json').read().decode())"
docker compose exec it-agent python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/.well-known/agent.json').read().decode())"
```
`"url": "http://kong-gateway:8000/hr-agent"` / `"http://kong-gateway:8000/it-agent"` が出力されれば正常です。

---

### 2-3. E2E テスト実施

#### 方法 A: Postman を使用する場合
リポジトリ直下の `Multi-Agent System Azure (A2A).postman_collection.json` をインポートし（`base_url` は `http://localhost:8000/main-agent` に設定済み）、ケース 0〜5 を順次実行します。

#### 方法 B: コマンドライン（PowerShell）で一括テストする場合
```powershell
$cases = @(
  @{ Name = "Case 1: HR Agent (E001)"; Body = '{"message": "従業員 E001 の基本情報を教えてください。"}' },
  @{ Name = "Case 2: IT Agent (Laptops)"; Body = '{"message": "現在利用可能なノートパソコンを教えてください。"}' },
  @{ Name = "Case 3: HR + IT Agent (E002 + Assign)"; Body = '{"message": "従業員 E002 の情報を確認し、利用可能なノートパソコンを1台割り当ててください。"}' },
  @{ Name = "Case 4: Salesforce Agent (No SF container -> graceful fallback)"; Body = '{"message": "Salesforce のタスク一覧を取得して整理してください。"}' },
  @{ Name = "Case 5: Empty Message (400)"; Body = '{"message": ""}' }
)
foreach ($c in $cases) {
  Write-Output "=== $($c.Name) ==="
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($c.Body)
  try {
    $r = Invoke-WebRequest -Uri "http://localhost:8000/main-agent/chat" -Method Post -ContentType "application/json; charset=utf-8" -Body $bytes -UseBasicParsing -TimeoutSec 120
    Write-Output "STATUS: $($r.StatusCode)"
    Write-Output ([System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()))
  } catch {
    $resp = $_.Exception.Response
    if ($resp) { Write-Output "STATUS: $([int]$resp.StatusCode)" } else { Write-Output "ERROR: $($_.Exception.Message)" }
  }
}
```

**macOS / Linux (Bash) の単発テスト例:**
```bash
curl -s -X POST http://localhost:8000/main-agent/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "従業員 E002 の情報を確認し、利用可能なノートパソコンを1台割り当ててください。"}'
```

---

### 2-4. Kong アクセスログでの 4 経路通過検証

```bash
docker logs --tail 80 kong-gateway
```

アクセスログに以下 4 種類のトラフィックがすべて記録されていれば、全通信の Kong AI Gateway 経由化が完了しています：

1. **クライアント ➔ Kong ➔ `main-agent`**: `GET /main-agent/health`, `POST /main-agent/chat`
2. **各 Agent ➔ Kong ➔ LLM**: `POST /v1/chat/completions`（`AsyncOpenAI/Python` および `OpenAI/Python`）
3. **`main-agent` ➔ Kong ➔ `hr-agent` / `it-agent`（A2A）**: `GET /hr-agent/.well-known/agent.json`, `GET /it-agent/.well-known/agent.json`, `POST /hr-agent/a2a`, `POST /it-agent/a2a`
4. **`hr-agent` / `it-agent` ➔ Kong ➔ `mcp-server`（MCP）**: `POST /mcp`, `GET /mcp`, `DELETE /mcp`

さらに、各 Agent / MCP コンテナのログを確認すると、受信元 IP がすべて `kong-gateway` のみに統一されていることを確認できます：
```bash
docker compose logs --tail 20 main-agent hr-agent it-agent mcp-server
```

---

## 6. クリーンアップ手順（Phase 2 ➔ Phase 1 の順）

1. **フェーズ 2（Agent / MCP）の停止・削除**:
   ```bash
   docker compose down
   ```
2. **フェーズ 1（Kong Data Plane・ネットワーク・Konnect 設定）の削除**:
   ```bash
   docker rm -f kong-gateway
   docker network rm agent_internal_net

   # Konnect 上の 6 エンティティを削除する場合（事前確認後に実行）
   kongctl delete -f kong-ai-gateway/ai-gateway.yaml --dry-run
   kongctl delete -f kong-ai-gateway/ai-gateway.yaml --auto-approve -o text
   ```
   （※ Control Plane 自体を方法 A/B で作成した場合は、必要に応じて Konnect UI または対応する `kongctl delete` で削除してください。）
