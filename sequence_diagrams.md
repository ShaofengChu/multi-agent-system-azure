# マルチエージェントシステム 通信シーケンス図（テストケース別）

本ドキュメントは、Postman テストコレクションの起動時ディスカバリ（0-A）および各テストケース（ケース 0〜5）における、クライアント・オーケストレーター（`main-agent`）・Azure OpenAI・サブエージェント（`hr-agent` / `it-agent` / `salesforce-agent`）・MCP サーバー間の通信シーケンスと送受信パラメータの詳細仕様をまとめたものです。

---

## 0-A. 【共通】起動時 / 未取得時の Agent Card 動的ディスカバリ

`main_agent/main.py` の起動時（`lifespan`）および `main_agent/agent.py` の `discover_agents()` によるサブエージェントのスキル自動取得と OpenAI Function Calling ツール定義への変換シーケンスです。

```mermaid
sequenceDiagram
    autonumber
    participant Main as main-agent<br/>(Port 8000)
    participant HR as hr-agent<br/>(http://hr-agent:8080)
    participant IT as it-agent<br/>(http://it-agent:8080)
    participant SF as salesforce-agent<br/>(http://salesforce-agent:8080)

    Note over Main: lifespan 起動時 または process_main_task() 実行時に<br/>未取得のエージェントに対して discover_agents() を実行 (timeout=10.0s)

    par asyncio.gather による並列ディスカバリ
        Main->>HR: GET http://hr-agent:8080/.well-known/agent.json
        Note left of HR: [Response 200 OK]<br/>{<br/>  "protocolVersion": "0.3.0",<br/>  "name": "HR Agent",<br/>  "description": "HR関連業務の処理：従業員情報の照会、入社プロセス",<br/>  "url": "http://hr-agent:8080",<br/>  "preferredTransport": "JSONRPC",<br/>  "version": "1.0.0",<br/>  "capabilities": {"streaming": false, "pushNotifications": false},<br/>  "defaultInputModes": ["text/plain", "application/json"],<br/>  "defaultOutputModes": ["text/plain", "application/json"],<br/>  "skills": [<br/>    {"id": "query_employee", "name": "従業員情報の照会", "description": "従業員IDに基づいて基本情報を取得する", "tags": ["query","employee","hr"]},<br/>    {"id": "onboard_employee", "name": "従業員入社", "description": "新入社員の入社手続きを行う", "tags": ["onboard","employee","hr"]}<br/>  ]<br/>}
        HR-->>Main: 200 OK (HR Agent Card JSON)
    and
        Main->>IT: GET http://it-agent:8080/.well-known/agent.json
        Note left of IT: [Response 200 OK]<br/>{<br/>  "protocolVersion": "0.3.0",<br/>  "name": "IT Agent",<br/>  "description": "IT機器関連業務の処理：機器の照会と割り当て",<br/>  "url": "http://it-agent:8080",<br/>  "preferredTransport": "JSONRPC",<br/>  "version": "1.0.0",<br/>  "capabilities": {"streaming": false, "pushNotifications": false},<br/>  "defaultInputModes": ["text/plain", "application/json"],<br/>  "defaultOutputModes": ["text/plain", "application/json"],<br/>  "skills": [<br/>    {"id": "query_equipment", "name": "機器照会", "description": "利用可能な機器を照会する", "tags": ["query","equipment"]},<br/>    {"id": "assign_equipment", "name": "機器割り当て", "description": "従業員に機器を割り当てる", "tags": ["assign","equipment"]}<br/>  ]<br/>}
        IT-->>Main: 200 OK (IT Agent Card JSON)
    and
        Main->>SF: GET http://salesforce-agent:8080/.well-known/agent.json
        Note left of SF: [Response 200 OK]<br/>{<br/>  "protocolVersion": "0.3.0",<br/>  "name": "Salesforce Agent",<br/>  "description": "Salesforceタスク管理：タスク情報の取得と照会",<br/>  "url": "http://salesforce-agent:8080",<br/>  "preferredTransport": "JSONRPC",<br/>  "version": "1.0.0",<br/>  "capabilities": {"streaming": false, "pushNotifications": false},<br/>  "defaultInputModes": ["text/plain", "application/json"],<br/>  "defaultOutputModes": ["text/plain", "application/json"],<br/>  "skills": [<br/>    {"id": "get_sf_task", "name": "Salesforceタスク取得", "description": "Salesforceからタスク情報を取得する", "tags": ["query","salesforce","task"]}<br/>  ]<br/>}
        SF-->>Main: 200 OK (Salesforce Agent Card JSON)
    end

    Note over Main: 取得した各 Agent Card から _openai_tools_cache を構築:<br/>[<br/>  {<br/>    "type": "function",<br/>    "function": {<br/>      "name": "call_hr_agent" | "call_it_agent" | "call_salesforce_agent",<br/>      "description": "<name>: <description>\n対応スキル:\n- <skill.name> (<skill.id>): <skill.description>",<br/>      "parameters": {<br/>        "type": "object",<br/>        "properties": { "query": { "type": "string", "description": "サブエージェントへ送信する具体的なタスク指示や質問内容" } },<br/>        "required": ["query"]<br/>      }<br/>    }<br/>  }<br/>]
```

---

## テストケース 0：ヘルスチェック (`GET /health`)

`main_agent/main.py` の稼働確認シーケンスです。

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent<br/>(http://localhost:8000)

    Client->>Main: GET http://localhost:8000/health
    Note right of Client: [Request]<br/>Method: GET<br/>URL: http://localhost:8000/health<br/>Headers: なし<br/>Body: なし

    Main-->>Client: 200 OK
    Note left of Main: [Response 200 OK]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "status": "ok",<br/>  "agent": "main-agent"<br/>}
```

---

## テストケース 1：HR エージェント単体（従業員情報の照会）

`main-agent` から `hr-agent`（`hr_agent/main.py`、`hr_agent/agent.py`）へ A2A で委譲し、`mcp-server`（`mcp_server/main.py`）の `get_employee_info` を実行するシーケンスです。

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent<br/>(Port 8000)
    participant AOAI as Azure OpenAI<br/>(gpt-5-mini)
    participant HR as hr-agent<br/>(Port 8080)
    participant MCP as mcp-server<br/>(Port 8080)

    Client->>Main: POST http://localhost:8000/chat
    Note right of Client: [Request]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "message": "従業員 E001 の基本情報を教えてください。"<br/>}

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions?api-version=2024-12-01-preview
    Note right of Main: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [<br/>  {"role": "system", "content": "あなたはマルチエージェントシステムのメインオーケストレーターです..."},<br/>  {"role": "user", "content": "従業員 E001 の基本情報を教えてください。"}<br/>]<br/>tools: [call_hr_agent, call_it_agent, call_salesforce_agent]

    AOAI-->>Main: 200 OK (finish_reason: "tool_calls")
    Note left of AOAI: [Output Parameters]<br/>choices[0].message.tool_calls: [<br/>  {<br/>    "id": "call_hr_01",<br/>    "type": "function",<br/>    "function": {<br/>      "name": "call_hr_agent",<br/>      "arguments": "{\"query\": \"従業員 E001 の基本情報を照会してください。\"}"<br/>    }<br/>  }<br/>]

    Main->>HR: POST http://hr-agent:8080/a2a (timeout=60.0s)
    Note right of Main: [A2A Request JSON-RPC 2.0]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "method": "tasks/send",<br/>  "id": "<request-uuid4>",<br/>  "params": {<br/>    "id": "<task-uuid4>",<br/>    "message": {<br/>      "role": "user",<br/>      "parts": [{"type": "text", "text": "従業員 E001 の基本情報を照会してください。"}]<br/>    }<br/>  }<br/>}

    rect rgb(240, 248, 255)
        Note over HR,MCP: MCP Streamable HTTP セッション初期化 (http://mcp-server:8080/mcp)
        HR->>MCP: POST /mcp (method: "initialize", params: {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "mcp", "version": "..."}})
        MCP-->>HR: 200 OK (Header: mcp-session-id: <session-id>)
        HR->>MCP: POST /mcp (Header: mcp-session-id, method: "notifications/initialized")
        MCP-->>HR: 202 Accepted
        HR->>MCP: GET /mcp (Header: mcp-session-id, Accept: text/event-stream)
        HR->>MCP: POST /mcp (Header: mcp-session-id, method: "tools/list", params: {})
        MCP-->>HR: 200 OK
        Note left of MCP: [MCP tools/list Output]<br/>tools: [<br/>  {"name": "get_employee_info", "inputSchema": {"type": "object", "properties": {"employee_id": {"type": "string"}}, "required": ["employee_id"]}},<br/>  {"name": "get_available_laptops", "inputSchema": {"type": "object", "properties": {}}},<br/>  {"name": "assign_equipment", "inputSchema": {"type": "object", "properties": {"employee_id": {"type": "string"}, "laptop_id": {"type": "string"}}, "required": ["employee_id", "laptop_id"]}}<br/>]
    end

    HR->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions?api-version=2024-12-01-preview
    Note right of HR: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [<br/>  {"role": "system", "content": "あなたはHRアシスタントです。従業員情報の照会と入社関連業務のみを担当します。機器の割り当ては職務範囲外ですので、ユーザーにIT部門へ連絡するよう伝えてください。"},<br/>  {"role": "user", "content": "従業員 E001 の基本情報を照会してください。"}<br/>]<br/>tools: [get_employee_info, get_available_laptops, assign_equipment]

    AOAI-->>HR: 200 OK (finish_reason: "tool_calls")
    Note left of AOAI: [Output Parameters]<br/>tool_calls: [<br/>  {<br/>    "id": "call_mcp_01",<br/>    "type": "function",<br/>    "function": {"name": "get_employee_info", "arguments": "{\"employee_id\": \"E001\"}"}<br/>  }<br/>]

    HR->>MCP: POST http://mcp-server:8080/mcp (Header: mcp-session-id)
    Note right of HR: [MCP tools/call Request]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "id": 2,<br/>  "method": "tools/call",<br/>  "params": {<br/>    "name": "get_employee_info",<br/>    "arguments": {"employee_id": "E001"}<br/>  }<br/>}

    MCP-->>HR: 200 OK
    Note left of MCP: [MCP tools/call Response]<br/>content: [<br/>  {<br/>    "type": "text",<br/>    "text": "{\"name\": \"田中 太郎\", \"dept\": \"engineering\", \"start_date\": \"2024-01-15\", \"email\": \"tanaka@demo.com\"}"<br/>  }<br/>]

    HR->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
    Note right of HR: [Input Parameters]<br/>messages: [..., assistant(tool_calls), {"role": "tool", "tool_call_id": "call_mcp_01", "content": "{\"name\": \"田中 太郎\", ...}"}]

    AOAI-->>HR: 200 OK (finish_reason: "stop", content: "従業員E001（田中 太郎）の基本情報は以下の通りです...")

    HR->>MCP: DELETE http://mcp-server:8080/mcp (Header: mcp-session-id)
    MCP-->>HR: 200 OK

    HR-->>Main: 200 OK (A2A Response JSON-RPC 2.0)
    Note left of HR: [A2A Response]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "id": "<request-uuid4>",<br/>  "result": {<br/>    "id": "<task-uuid4>",<br/>    "contextId": "<request-uuid4>",<br/>    "kind": "task",<br/>    "status": {<br/>      "state": "completed",<br/>      "message": {"role": "agent", "parts": [{"type": "text", "text": "従業員E001（田中 太郎）の基本情報は以下の通りです..."}]}<br/>    },<br/>    "artifacts": [<br/>      {"artifactId": "<artifact-uuid4>", "parts": [{"type": "text", "text": "従業員E001（田中 太郎）の基本情報は以下の通りです...", "kind": "text"}]}<br/>    ]<br/>  }<br/>}

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
    Note right of Main: [Input Parameters]<br/>messages: [..., assistant(tool_calls), {"role": "tool", "tool_call_id": "call_hr_01", "content": "従業員E001（田中 太郎）の基本情報は以下の通りです..."}]

    AOAI-->>Main: 200 OK (finish_reason: "stop", content: "従業員 E001 の基本情報をお知らせします...")

    Main-->>Client: 200 OK
    Note left of Main: [Response 200 OK]<br/>{<br/>  "response": "従業員 E001 の基本情報をお知らせします。\n- 氏名: 田中 太郎\n- 部署: engineering\n- 入社日: 2024-01-15\n- メール: tanaka@demo.com"<br/>}
```

---

## テストケース 2：IT エージェント単体（利用可能なノート PC の照会）

`main-agent` から `it-agent`（`it_agent/main.py`、`it_agent/agent.py`）へ A2A で委譲し、`mcp-server` の `get_available_laptops` を実行するシーケンスです。

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent<br/>(Port 8000)
    participant AOAI as Azure OpenAI<br/>(gpt-5-mini)
    participant IT as it-agent<br/>(Port 8080)
    participant MCP as mcp-server<br/>(Port 8080)

    Client->>Main: POST http://localhost:8000/chat
    Note right of Client: [Request]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "message": "現在利用可能なノートパソコンを教えてください。"<br/>}

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions?api-version=2024-12-01-preview
    Note right of Main: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [<br/>  {"role": "system", "content": "あなたはマルチエージェントシステムのメインオーケストレーターです..."},<br/>  {"role": "user", "content": "現在利用可能なノートパソコンを教えてください。"}<br/>]<br/>tools: [call_hr_agent, call_it_agent, call_salesforce_agent]

    AOAI-->>Main: 200 OK (finish_reason: "tool_calls")
    Note left of AOAI: [Output Parameters]<br/>choices[0].message.tool_calls: [<br/>  {<br/>    "id": "call_it_01",<br/>    "type": "function",<br/>    "function": {<br/>      "name": "call_it_agent",<br/>      "arguments": "{\"query\": \"現在利用可能なノートパソコンの一覧を照会してください。\"}"<br/>    }<br/>  }<br/>]

    Main->>IT: POST http://it-agent:8080/a2a (timeout=60.0s)
    Note right of Main: [A2A Request JSON-RPC 2.0]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "method": "tasks/send",<br/>  "id": "<request-uuid4>",<br/>  "params": {<br/>    "id": "<task-uuid4>",<br/>    "message": {<br/>      "role": "user",<br/>      "parts": [{"type": "text", "text": "現在利用可能なノートパソコンの一覧を照会してください。"}]<br/>    }<br/>  }<br/>}

    rect rgb(240, 248, 255)
        Note over IT,MCP: MCP Streamable HTTP セッション初期化 (http://mcp-server:8080/mcp)
        IT->>MCP: POST /mcp (initialize -> notifications/initialized -> GET /mcp -> tools/list)
        MCP-->>IT: 200 OK (Header: mcp-session-id, tools=[get_employee_info, get_available_laptops, assign_equipment])
    end

    IT->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions?api-version=2024-12-01-preview
    Note right of IT: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [<br/>  {"role": "system", "content": "あなたはIT機器管理アシスタントです。機器の照会と割り当て業務のみを担当します。必要に応じてツールを呼び出して従業員情報を取得できますが、機器の割り当てが主な職務です。"},<br/>  {"role": "user", "content": "現在利用可能なノートパソコンの一覧を照会してください。"}<br/>]<br/>tools: [get_employee_info, get_available_laptops, assign_equipment]

    AOAI-->>IT: 200 OK (finish_reason: "tool_calls")
    Note left of AOAI: [Output Parameters]<br/>tool_calls: [<br/>  {<br/>    "id": "call_mcp_it_01",<br/>    "type": "function",<br/>    "function": {"name": "get_available_laptops", "arguments": "{}"}<br/>  }<br/>]

    IT->>MCP: POST http://mcp-server:8080/mcp (Header: mcp-session-id)
    Note right of IT: [MCP tools/call Request]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "id": 2,<br/>  "method": "tools/call",<br/>  "params": {<br/>    "name": "get_available_laptops",<br/>    "arguments": {}<br/>  }<br/>}

    MCP-->>IT: 200 OK
    Note left of MCP: [MCP tools/call Response]<br/>content: [<br/>  {"type": "text", "text": "{\"id\": \"L001\", \"model\": \"MacBook Pro 14\", \"status\": \"available\"}"},<br/>  {"type": "text", "text": "{\"id\": \"L002\", \"model\": \"ThinkPad X1 Carbon\", \"status\": \"available\"}"}<br/>]<br/>※ L003 (Dell XPS 15) は status="assigned" (assigned_to="E001") のため除外

    IT->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
    Note right of IT: [Input Parameters]<br/>messages: [..., assistant(tool_calls), {"role": "tool", "tool_call_id": "call_mcp_it_01", "content": "{\"id\": \"L001\"...}\n{\"id\": \"L002\"...}"}]

    AOAI-->>IT: 200 OK (finish_reason: "stop", content: "現在利用可能なノートパソコンは L001 (MacBook Pro 14) と L002 (ThinkPad X1 Carbon) の2台です。")

    IT->>MCP: DELETE http://mcp-server:8080/mcp (Header: mcp-session-id)
    MCP-->>IT: 200 OK

    IT-->>Main: 200 OK (A2A Response JSON-RPC 2.0)
    Note left of IT: [A2A Response]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "id": "<request-uuid4>",<br/>  "result": {<br/>    "id": "<task-uuid4>",<br/>    "contextId": "<request-uuid4>",<br/>    "kind": "task",<br/>    "status": {"state": "completed", "message": {"role": "agent", "parts": [{"type": "text", "text": "現在利用可能なノートパソコンは..."}]}},<br/>    "artifacts": [{"artifactId": "<artifact-uuid4>", "parts": [{"type": "text", "text": "現在利用可能なノートパソコンは...", "kind": "text"}]}]<br/>  }<br/>}

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
    Note right of Main: [Input Parameters]<br/>messages: [..., assistant(tool_calls), {"role": "tool", "tool_call_id": "call_it_01", "content": "現在利用可能なノートパソコンは..."}]

    AOAI-->>Main: 200 OK (finish_reason: "stop")

    Main-->>Client: 200 OK
    Note left of Main: [Response 200 OK]<br/>{<br/>  "response": "現在利用可能なノートパソコンは以下の2台です。\n- L001: MacBook Pro 14 (available)\n- L002: ThinkPad X1 Carbon (available)"<br/>}
```

---

## テストケース 3：HR + IT エージェント連携（従業員確認と PC 割り当て）

`main-agent` が `call_hr_agent` と `call_it_agent` を並列呼び出しし、`it-agent` 内で `get_available_laptops` → `assign_equipment` の 2 段階ツール呼び出しを行うシーケンスです。

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent<br/>(Port 8000)
    participant AOAI as Azure OpenAI<br/>(gpt-5-mini)
    participant HR as hr-agent<br/>(Port 8080)
    participant IT as it-agent<br/>(Port 8080)
    participant MCP as mcp-server<br/>(Port 8080)

    Client->>Main: POST http://localhost:8000/chat
    Note right of Client: [Request]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "message": "従業員 E002 の情報を確認し、利用可能なノートパソコンを1台割り当ててください。"<br/>}

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions?api-version=2024-12-01-preview
    Note right of Main: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [system, {"role": "user", "content": "従業員 E002 の情報を確認し、利用可能なノートパソコンを1台割り当ててください。"}]<br/>tools: [call_hr_agent, call_it_agent, call_salesforce_agent]

    AOAI-->>Main: 200 OK (finish_reason: "tool_calls")
    Note left of AOAI: [Output Parameters: 2件の並列 tool_calls]<br/>1. id="call_hr_02", name="call_hr_agent",<br/>   arguments="{\"query\": \"従業員 E002 の基本情報を確認してください。\"}"<br/>2. id="call_it_02", name="call_it_agent",<br/>   arguments="{\"query\": \"従業員 E002 に利用可能なノートパソコンを1台割り当ててください。\"}"

    par asyncio.gather による HR / IT サブエージェント並列 A2A 呼び出し
        Main->>HR: POST http://hr-agent:8080/a2a
        Note right of Main: [A2A Request 1]<br/>method: "tasks/send"<br/>params.message.parts: [{"type": "text", "text": "従業員 E002 の基本情報を確認してください。"}]

        HR->>MCP: POST /mcp (initialize -> notifications/initialized -> tools/list)
        MCP-->>HR: 200 OK (mcp-session-id: <session-hr>)

        HR->>AOAI: chat.completions.create (messages=[hr_system, user], tools=[MCP 3ツール])
        AOAI-->>HR: tool_calls: id="call_mcp_hr", name="get_employee_info", arguments="{\"employee_id\": \"E002\"}"

        HR->>MCP: POST /mcp (method: "tools/call")
        Note right of HR: [MCP tools/call Input]<br/>name: "get_employee_info"<br/>arguments: {"employee_id": "E002"}
        MCP-->>HR: 200 OK
        Note left of MCP: [MCP tools/call Output]<br/>{"name": "佐藤 次郎", "dept": "marketing", "start_date": "2024-03-01", "email": "sato@demo.com"}

        HR->>AOAI: chat.completions.create (role="tool" 結果反映)
        AOAI-->>HR: finish_reason="stop" (E002 従業員情報テキスト)
        HR->>MCP: DELETE /mcp (mcp-session-id: <session-hr>)
        HR-->>Main: 200 OK (A2A Task Result: E002 佐藤 次郎の情報)
    and
        Main->>IT: POST http://it-agent:8080/a2a
        Note right of Main: [A2A Request 2]<br/>method: "tasks/send"<br/>params.message.parts: [{"type": "text", "text": "従業員 E002 に利用可能なノートパソコンを1台割り当ててください。"}]

        IT->>MCP: POST /mcp (initialize -> notifications/initialized -> tools/list)
        MCP-->>IT: 200 OK (mcp-session-id: <session-it>)

        IT->>AOAI: chat.completions.create (Loop 1回目: 空き機器照会判断)
        AOAI-->>IT: tool_calls: id="call_mcp_it_1", name="get_available_laptops", arguments="{}"

        IT->>MCP: POST /mcp (method: "tools/call")
        Note right of IT: [MCP tools/call Input 1]<br/>name: "get_available_laptops"<br/>arguments: {}
        MCP-->>IT: 200 OK
        Note left of MCP: [MCP tools/call Output 1]<br/>[{"id": "L001", "model": "MacBook Pro 14", "status": "available"},<br/> {"id": "L002", "model": "ThinkPad X1 Carbon", "status": "available"}]

        IT->>AOAI: chat.completions.create (Loop 2回目: 空き機器リストから1台選択し割当実行)
        AOAI-->>IT: tool_calls: id="call_mcp_it_2", name="assign_equipment", arguments="{\"employee_id\": \"E002\", \"laptop_id\": \"L001\"}"

        IT->>MCP: POST /mcp (method: "tools/call")
        Note right of IT: [MCP tools/call Input 2]<br/>name: "assign_equipment"<br/>arguments: {"employee_id": "E002", "laptop_id": "L001"}
        MCP-->>IT: 200 OK
        Note left of MCP: [MCP tools/call Output 2]<br/>LAPTOPS 内の L001 を status="assigned", assigned_to="E002" に更新<br/>{"success": true, "message": "L001 を E002 に割り当てました"}

        IT->>AOAI: chat.completions.create (Loop 3回目: 割当完了結果の反映)
        AOAI-->>IT: finish_reason="stop" (L001 割当完了テキスト)
        IT->>MCP: DELETE /mcp (mcp-session-id: <session-it>)
        IT-->>Main: 200 OK (A2A Task Result: L001 を E002 に割当完了)
    end

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
    Note right of Main: [Input Parameters]<br/>messages: [<br/>  ...,<br/>  assistant(tool_calls=[call_hr_02, call_it_02]),<br/>  {"role": "tool", "tool_call_id": "call_hr_02", "content": "従業員 E002（佐藤 次郎）の情報..."},<br/>  {"role": "tool", "tool_call_id": "call_it_02", "content": "ノートPC L001（MacBook Pro 14）を E002 に割り当てました..."}<br/>]

    AOAI-->>Main: 200 OK (finish_reason: "stop", 統合回答テキスト)

    Main-->>Client: 200 OK
    Note left of Main: [Response 200 OK]<br/>{<br/>  "response": "1) 従業員情報（HR照会結果）\n- 従業員ID: E002 / 氏名: 佐藤 次郎 / 部署: marketing / 入社日: 2024-03-01 / メール: sato@demo.com\n2) ノートPC割り当て（IT処理結果）\n- 機器ID: L001 (MacBook Pro 14) を E002 に割り当て完了しました。"<br/>}
```

---

## テストケース 4：Salesforce エージェント単体（Salesforce タスク一覧取得）

`main-agent` から `salesforce-agent`（`salesforce_agent/main.py`、`salesforce_agent/agent.py`）へ A2A で委譲し、外部 Salesforce MCP サーバーの `getSFTask` を呼び出すシーケンス（正常系および外部 MCP サーバー到達不能時のフォールバック系の両方を含む）です。

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent<br/>(Port 8000)
    participant AOAI as Azure OpenAI<br/>(gpt-5-mini)
    participant SF as salesforce-agent<br/>(Port 8080)
    participant SFMCP as 外部 Salesforce MCP Server<br/>(CloudHub /mcp)

    Client->>Main: POST http://localhost:8000/chat
    Note right of Client: [Request]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "message": "Salesforce のタスク一覧を取得して整理してください。"<br/>}

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions?api-version=2024-12-01-preview
    Note right of Main: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [system, {"role": "user", "content": "Salesforce のタスク一覧を取得して整理してください。"}]<br/>tools: [call_hr_agent, call_it_agent, call_salesforce_agent]

    AOAI-->>Main: 200 OK (finish_reason: "tool_calls")
    Note left of AOAI: [Output Parameters]<br/>tool_calls: [<br/>  {<br/>    "id": "call_sf_01",<br/>    "type": "function",<br/>    "function": {<br/>      "name": "call_salesforce_agent",<br/>      "arguments": "{\"query\": \"Salesforce のタスク一覧を取得して整理してください。\"}"<br/>    }<br/>  }<br/>]

    Main->>SF: POST http://salesforce-agent:8080/a2a (timeout=60.0s)
    Note right of Main: [A2A Request JSON-RPC 2.0]<br/>{<br/>  "jsonrpc": "2.0",<br/>  "method": "tasks/send",<br/>  "id": "<request-uuid4>",<br/>  "params": {<br/>    "id": "<task-uuid4>",<br/>    "message": {<br/>      "role": "user",<br/>      "parts": [{"type": "text", "text": "Salesforce のタスク一覧を取得して整理してください。"}]<br/>    }<br/>  }<br/>}

    alt 正常系：外部 Salesforce MCP サーバーが稼働・到達可能な場合
        SF->>SFMCP: POST https://mulesoft-generative-ai-mcp-server-4aa6a9.zlqs1p.jpn-e1.cloudhub.io/mcp
        Note right of SF: [MCP Handshake & tools/list]<br/>1. initialize -> 200 OK (mcp-session-id)<br/>2. notifications/initialized -> 202 Accepted<br/>3. tools/list -> 200 OK
        SFMCP-->>SF: 200 OK (tools リスト返却)
        Note over SF: list_tools() の結果から<br/>t.name == "getSFTask" のみフィルタリングして openai_tools に登録

        SF->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
        Note right of SF: [Input Parameters]<br/>model: "gpt-5-mini"<br/>messages: [<br/>  {"role": "system", "content": "あなたはSalesforceタスク管理アシスタントです。Salesforceのカスタムオブジェクトからタスク情報を取得し、ユーザーに分かりやすく提供します。タスクの項目は、タスク名(Name)、分類(Category__c)、ステータス(Status__c)、予定開始日(Planned_Start__c)、予定終了日(Planned_End__c)、実績開始日(Actual_Start__c)、実績終了日(Actual_End__c)、コメント(Comments__c)です。getSFTaskツールを使ってタスク一覧を取得し、結果をわかりやすく整理して回答してください。"},<br/>  {"role": "user", "content": "Salesforce のタスク一覧を取得して整理してください。"}<br/>]<br/>tools: [getSFTask]

        AOAI-->>SF: 200 OK (finish_reason: "tool_calls")
        Note left of AOAI: [Output Parameters]<br/>tool_calls: [{"id": "call_sftask_01", "type": "function", "function": {"name": "getSFTask", "arguments": "{}"}}]

        SF->>SFMCP: POST /mcp (method: "tools/call")
        Note right of SF: [MCP tools/call Input]<br/>{"name": "getSFTask", "arguments": {}}

        SFMCP-->>SF: 200 OK
        Note left of SFMCP: [MCP tools/call Output]<br/>[{"Name": "...", "Category__c": "...", "Status__c": "...",<br/>  "Planned_Start__c": "...", "Planned_End__c": "...",<br/>  "Actual_Start__c": "...", "Actual_End__c": "...", "Comments__c": "..."}]

        SF->>AOAI: chat.completions.create (role="tool" でタスク一覧JSONを渡す)
        AOAI-->>SF: 200 OK (finish_reason: "stop", 整理済みタスク一覧テキスト)
        SF->>SFMCP: DELETE /mcp
        SF-->>Main: 200 OK (A2A Task Result: status.state="completed", artifacts=[整理済みタスク一覧])
    else フォールバック系：外部 Salesforce MCP サーバーが停止・接続不可の場合
        SF->>SFMCP: POST https://mulesoft-generative-ai-mcp-server-4aa6a9.zlqs1p.jpn-e1.cloudhub.io/mcp (initialize)
        SFMCP--xSF: httpx.ConnectError: All connection attempts failed
        SF-->>Main: 500 Internal Server Error
        Note over Main: _execute_tool_call() が httpx.HTTPStatusError をキャッチし<br/>例外を握りつぶして以下の文字列を返却:<br/>"エラー: Salesforce Agent (http://salesforce-agent:8080) との通信に失敗しました:<br/>Server error '500 Internal Server Error' for url 'http://salesforce-agent:8080/a2a'"
    end

    Main->>AOAI: POST /openai/deployments/gpt-5-mini/chat/completions
    Note right of Main: [Input Parameters]<br/>messages: [..., assistant(tool_calls), {"role": "tool", "tool_call_id": "call_sf_01", "content": "<整理済みタスク一覧 または エラー文字列>"}]

    AOAI-->>Main: 200 OK (finish_reason: "stop", 最終回答または代替案提示テキスト)

    Main-->>Client: 200 OK
    Note left of Main: [Response 200 OK]<br/>{<br/>  "response": "<整理されたSalesforceタスク一覧 または 接続エラー報告と再試行・代替案の案内>"<br/>}
```

---

## テストケース 5：異常系（空メッセージによるバリデーションエラー `400 Bad Request`）

`main_agent/main.py` の入力値検証で弾かれ、Azure OpenAI や各サブエージェントへの通信が発生しないシーケンスです。

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent<br/>(http://localhost:8000)

    Client->>Main: POST http://localhost:8000/chat
    Note right of Client: [Request]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "message": ""<br/>}<br/>※ {"query": "   "} や {} (両方 null) の場合も同様

    Note over Main: [バリデーション処理 (main_agent/main.py)]<br/>req = ChatRequest(message="", query=None)<br/>user_text = (req.message or req.query or "").strip() -> ""<br/>if not user_text:<br/>  raise HTTPException(status_code=400, detail="...")

    Main-->>Client: 400 Bad Request
    Note left of Main: [Response 400 Bad Request]<br/>Headers: Content-Type: application/json<br/>Body:<br/>{<br/>  "detail": "リクエストボディに空でない 'message' または 'query' を指定してください。"<br/>}
```


---

# 簡易版シーケンス図（全体通信フロー）

以下は、各ケースの送受信パラメータ詳細を省略し、全体の通信経路と処理の流れを俯瞰するための簡易版シーケンス図です。

---

## 0-A（簡易版）. 【共通】起動時 / 未取得時の Agent Card 動的ディスカバリ

```mermaid
sequenceDiagram
    autonumber
    participant Main as main-agent
    participant HR as hr-agent
    participant IT as it-agent
    participant SF as salesforce-agent

    par 並列ディスカバリ
        Main->>HR: GET /.well-known/agent.json
        HR-->>Main: 200 OK (Agent Card)
    and
        Main->>IT: GET /.well-known/agent.json
        IT-->>Main: 200 OK (Agent Card)
    and
        Main->>SF: GET /.well-known/agent.json
        SF-->>Main: 200 OK (Agent Card)
    end
    Note over Main: 各スキルを OpenAI Tool に動的登録
```

---

## テストケース 0（簡易版）：ヘルスチェック (`GET /health`)

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent

    Client->>Main: GET /health
    Main-->>Client: 200 OK (稼働確認)
```

---

## テストケース 1（簡易版）：HR エージェント単体（従業員情報の照会）

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent
    participant AOAI as Azure OpenAI
    participant HR as hr-agent
    participant MCP as mcp-server

    Client->>Main: POST /chat (E001 情報照会)
    Main->>AOAI: ルーティング判断
    AOAI-->>Main: call_hr_agent を選択
    Main->>HR: POST /a2a (tasks/send)
    HR->>MCP: MCP セッション開始・ツール取得
    HR->>AOAI: ツール選択
    AOAI-->>HR: get_employee_info を選択
    HR->>MCP: get_employee_info 実行
    MCP-->>HR: 従業員データ返却
    HR->>AOAI: 回答生成
    AOAI-->>HR: HR 回答テキスト
    HR->>MCP: MCP セッション終了
    HR-->>Main: 200 OK (A2A タスク完了)
    Main->>AOAI: 最終回答生成
    AOAI-->>Main: 最終回答テキスト
    Main-->>Client: 200 OK (レスポンス返却)
```

---

## テストケース 2（簡易版）：IT エージェント単体（利用可能なノート PC の照会）

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent
    participant AOAI as Azure OpenAI
    participant IT as it-agent
    participant MCP as mcp-server

    Client->>Main: POST /chat (空きノートPC照会)
    Main->>AOAI: ルーティング判断
    AOAI-->>Main: call_it_agent を選択
    Main->>IT: POST /a2a (tasks/send)
    IT->>MCP: MCP セッション開始・ツール取得
    IT->>AOAI: ツール選択
    AOAI-->>IT: get_available_laptops を選択
    IT->>MCP: get_available_laptops 実行
    MCP-->>IT: 空き PC リスト返却
    IT->>AOAI: 回答生成
    AOAI-->>IT: IT 回答テキスト
    IT->>MCP: MCP セッション終了
    IT-->>Main: 200 OK (A2A タスク完了)
    Main->>AOAI: 最終回答生成
    AOAI-->>Main: 最終回答テキスト
    Main-->>Client: 200 OK (レスポンス返却)
```

---

## テストケース 3（簡易版）：HR + IT エージェント連携（従業員確認と PC 割り当て）

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent
    participant AOAI as Azure OpenAI
    participant HR as hr-agent
    participant IT as it-agent
    participant MCP as mcp-server

    Client->>Main: POST /chat (E002確認 & PC割り当て)
    Main->>AOAI: タスク分解・ルーティング判断
    AOAI-->>Main: call_hr_agent + call_it_agent (並列)

    par 並列 A2A オーケストレーション
        Main->>HR: POST /a2a (E002 照会)
        HR->>MCP: セッション開始 & get_employee_info
        MCP-->>HR: E002 情報返却
        HR->>AOAI: HR 回答生成
        HR->>MCP: セッション終了
        HR-->>Main: 200 OK (E002 情報)
    and
        Main->>IT: POST /a2a (E002 へ PC 割り当て)
        IT->>MCP: セッション開始 & get_available_laptops
        MCP-->>IT: 空き PC 一覧返却
        IT->>AOAI: 割当対象を決定
        IT->>MCP: assign_equipment 実行
        MCP-->>IT: 割り当て完了
        IT->>AOAI: IT 回答生成
        IT->>MCP: セッション終了
        IT-->>Main: 200 OK (割り当て結果)
    end

    Main->>AOAI: 複数サブエージェント結果を集約
    AOAI-->>Main: 統合回答テキスト
    Main-->>Client: 200 OK (統合レスポンス返却)
```

---

## テストケース 4（簡易版）：Salesforce エージェント単体（Salesforce タスク一覧取得）

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent
    participant AOAI as Azure OpenAI
    participant SF as salesforce-agent
    participant SFMCP as 外部 Salesforce MCP Server

    Client->>Main: POST /chat (Salesforce タスク照会)
    Main->>AOAI: ルーティング判断
    AOAI-->>Main: call_salesforce_agent を選択
    Main->>SF: POST /a2a (tasks/send)

    alt 外部 Salesforce MCP が到達可能な場合
        SF->>SFMCP: MCP セッション開始・ツール取得 (getSFTask)
        SF->>AOAI: ツール選択
        SF->>SFMCP: getSFTask 実行
        SFMCP-->>SF: タスク一覧返却
        SF->>AOAI: 結果整理・回答生成
        SF->>SFMCP: MCP セッション終了
        SF-->>Main: 200 OK (タスク一覧)
    else 外部 Salesforce MCP が接続不可の場合
        SF->>SFMCP: MCP 接続試行
        SFMCP--xSF: ConnectError
        SF-->>Main: 500 Internal Server Error
        Note over Main: 例外を捕捉しエラー内容を文字列で保持
    end

    Main->>AOAI: 最終回答（または代替案）生成
    AOAI-->>Main: 最終回答テキスト
    Main-->>Client: 200 OK (レスポンス返却)
```

---

## テストケース 5（簡易版）：異常系（空メッセージによるバリデーションエラー）

```mermaid
sequenceDiagram
    autonumber
    participant Client as Postman
    participant Main as main-agent

    Client->>Main: POST /chat (空メッセージ)
    Note over Main: 入力チェックでエラー（LLM / サブエージェント未呼び出し）
    Main-->>Client: 400 Bad Request
```
