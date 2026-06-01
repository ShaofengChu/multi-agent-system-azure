from openai import AzureOpenAI
import os, json
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

MCP_URL = os.environ.get(
    "SALESFORCE_MCP_SERVER_URL",
    "https://mulesoft-generative-ai-mcp-server-4aa6a9.zlqs1p.jpn-e1.cloudhub.io/mcp",
)

client = AzureOpenAI(
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.environ["AZURE_OPENAI_API_KEY"],
    api_version=os.environ.get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview"),
)

DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")

async def process_salesforce_task(user_input: str) -> str:
    async with streamablehttp_client(MCP_URL) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # MCPツールを取得してOpenAI tools形式に変換（getSFTaskのみ使用）
            mcp_tools = await session.list_tools()
            openai_tools = []

            for t in mcp_tools.tools:
                if t.name != "getSFTask":
                    continue
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                    }
                })

            messages = [
                {
                    "role": "system",
                    "content": (
                        "あなたはSalesforceタスク管理アシスタントです。"
                        "Salesforceのカスタムオブジェクトからタスク情報を取得し、ユーザーに分かりやすく提供します。"
                        "タスクの項目は、タスク名(Name)、分類(Category__c)、ステータス(Status__c)、"
                        "予定開始日(Planned_Start__c)、予定終了日(Planned_End__c)、"
                        "実績開始日(Actual_Start__c)、実績終了日(Actual_End__c)、コメント(Comments__c)です。"
                        "getSFTaskツールを使ってタスク一覧を取得し、結果をわかりやすく整理して回答してください。"
                    ),
                },
                {"role": "user", "content": user_input},
            ]

            response = client.chat.completions.create(
                model=DEPLOYMENT_NAME,
                messages=messages,
                tools=openai_tools if openai_tools else None,
            )

            # ツール呼び出しループの処理
            for _ in range(5):  # 無限ループを防ぐため、最大5回のツール呼び出し
                choice = response.choices[0]

                if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
                    break

                # Append the assistant message with tool_calls to the conversation
                messages.append(choice.message)

                for tool_call in choice.message.tool_calls:
                    func = tool_call.function
                    args_dict = json.loads(func.arguments) if func.arguments else {}
                    tool_result = await session.call_tool(func.name, args_dict)

                    # Extract text safely from MCP tool result
                    result_text = "\n".join(
                        item.text for item in tool_result.content if hasattr(item, "text")
                    ) if tool_result.content else "No result"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result_text,
                    })

                response = client.chat.completions.create(
                    model=DEPLOYMENT_NAME,
                    messages=messages,
                    tools=openai_tools if openai_tools else None,
                )

            return response.choices[0].message.content or ""
