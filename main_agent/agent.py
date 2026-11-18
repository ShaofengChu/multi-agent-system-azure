import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

DEPLOYMENT_NAME = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5-mini")

AGENT_CONFIGS: dict[str, dict[str, str]] = {
    "call_hr_agent": {
        "url": os.environ.get("HR_AGENT_URL", "http://quizzical_kepler:8000/hr-agent").rstrip("/"),
        "fallback_name": "HR Agent",
        "fallback_description": "HR関連業務（従業員情報の照会、入社プロセスなど）を処理するサブエージェントに問い合わせます。",
    },
    "call_it_agent": {
        "url": os.environ.get("IT_AGENT_URL", "http://quizzical_kepler:8000/it-agent").rstrip("/"),
        "fallback_name": "IT Agent",
        "fallback_description": "IT機器関連業務（機器の照会、従業員への割り当てなど）を処理するサブエージェントに問い合わせます。",
    },
}

_discovered_cards: dict[str, dict[str, Any]] = {}
_openai_tools_cache: dict[str, dict[str, Any]] = {}
_client: AsyncOpenAI | None = None


def _resolve_openai_base_url() -> str:
    """Resolve the OpenAI-compatible Kong AI Gateway base URL ending in /v1."""
    raw = (
        os.environ.get("OPENAI_BASE_URL")
        or os.environ.get("AZURE_OPENAI_ENDPOINT")
        or "http://quizzical_kepler:8000/v1"
    ).rstrip("/")
    return raw if raw.endswith("/v1") else f"{raw}/v1"


def _get_openai_client() -> AsyncOpenAI:
    """Lazily initialize the AsyncOpenAI client routed through Kong AI Gateway."""
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            base_url=_resolve_openai_base_url(),
            api_key=os.environ.get("AZURE_OPENAI_API_KEY")
            or os.environ.get("OPENAI_API_KEY")
            or "kong-managed",
        )
    return _client


def _build_tool_definition(
    tool_name: str,
    description: str,
) -> dict[str, Any]:
    """Construct an OpenAI Function Calling tool schema for delegating to a subagent."""
    return {
        "type": "function",
        "function": {
            "name": tool_name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "サブエージェントへ送信する具体的なタスク指示や質問内容",
                    }
                },
                "required": ["query"],
            },
        },
    }


def _format_card_description(card: dict[str, Any], fallback: str) -> str:
    """Format an Agent Card's metadata and skills into an OpenAI tool description."""
    name = card.get("name", "")
    description = card.get("description", fallback)
    skills = card.get("skills", [])

    parts = [f"{name}: {description}" if name else description]
    if isinstance(skills, list) and skills:
        skill_lines = []
        for skill in skills:
            if not isinstance(skill, dict):
                continue
            skill_id = skill.get("id", "")
            skill_name = skill.get("name", "")
            skill_desc = skill.get("description", "")
            label = f"{skill_name} ({skill_id})" if skill_id else skill_name
            skill_lines.append(f"- {label}: {skill_desc}".strip())
        if skill_lines:
            parts.append("対応スキル:\n" + "\n".join(skill_lines))
    return "\n".join(parts)


async def _fetch_agent_card(client: httpx.AsyncClient, tool_name: str, cfg: dict[str, str]) -> None:
    """Fetch /.well-known/agent.json for a single subagent and update the tool cache."""
    card_url = f"{cfg['url']}/.well-known/agent.json"
    try:
        resp = await client.get(card_url)
        resp.raise_for_status()
        card = resp.json()
        _discovered_cards[tool_name] = card
        description = _format_card_description(card, cfg["fallback_description"])
        _openai_tools_cache[tool_name] = _build_tool_definition(tool_name, description)
        logger.info("Discovered A2A agent '%s' from %s", card.get("name", tool_name), card_url)
    except Exception as exc:
        logger.warning("Failed to discover agent card from %s: %s", card_url, exc)
        if tool_name not in _openai_tools_cache:
            _openai_tools_cache[tool_name] = _build_tool_definition(
                tool_name,
                f"{cfg['fallback_name']}: {cfg['fallback_description']}",
            )


async def discover_agents(force: bool = False) -> list[dict[str, Any]]:
    """Discover subagent capabilities via /.well-known/agent.json and return OpenAI tools."""
    pending = {
        name: cfg
        for name, cfg in AGENT_CONFIGS.items()
        if force or name not in _discovered_cards
    }
    if pending:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await asyncio.gather(
                *(_fetch_agent_card(client, name, cfg) for name, cfg in pending.items())
            )
    return [_openai_tools_cache[name] for name in AGENT_CONFIGS if name in _openai_tools_cache]


def _extract_a2a_result_text(response_json: dict[str, Any]) -> str:
    """Extract text content from a standard A2A JSON-RPC 2.0 task response."""
    if "error" in response_json and response_json["error"]:
        err = response_json["error"]
        message = err.get("message", str(err)) if isinstance(err, dict) else str(err)
        raise RuntimeError(f"A2A error response: {message}")

    result = response_json.get("result")
    if not isinstance(result, dict):
        return json.dumps(response_json, ensure_ascii=False)

    texts: list[str] = []
    for artifact in result.get("artifacts", []):
        if not isinstance(artifact, dict):
            continue
        for part in artifact.get("parts", []):
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                texts.append(part["text"])

    if not texts:
        status_message = result.get("status", {}).get("message", {})
        if isinstance(status_message, dict):
            for part in status_message.get("parts", []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    texts.append(part["text"])

    if texts:
        return "\n".join(texts)
    return json.dumps(result, ensure_ascii=False)


async def send_a2a_task(agent_url: str, query: str) -> str:
    """Send a JSON-RPC 2.0 tasks/send request to a subagent's /a2a endpoint."""
    request_id = str(uuid.uuid4())
    payload = {
        "jsonrpc": "2.0",
        "method": "tasks/send",
        "id": request_id,
        "params": {
            "id": str(uuid.uuid4()),
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": query}],
            },
        },
    }
    base = agent_url.rstrip("/")
    endpoint = base if base.endswith("/a2a") else f"{base}/a2a"
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(endpoint, json=payload)
        resp.raise_for_status()
        return _extract_a2a_result_text(resp.json())


async def _execute_tool_call(tool_name: str, arguments_json: str) -> str:
    """Execute a single OpenAI tool call by dispatching an A2A task to the target subagent."""
    cfg = AGENT_CONFIGS.get(tool_name)
    if cfg is None:
        return f"エラー: 未知のツール '{tool_name}' が指定されました。"

    try:
        args = json.loads(arguments_json) if arguments_json else {}
    except json.JSONDecodeError as exc:
        return f"エラー: ツール引数の JSON 解析に失敗しました: {exc}"

    query = args.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return "エラー: 'query' パラメータが空です。"

    card_url = _discovered_cards.get(tool_name, {}).get("url")
    target_url = (
        card_url.rstrip("/")
        if isinstance(card_url, str) and card_url.strip()
        else cfg["url"]
    )
    try:
        return await send_a2a_task(target_url, query)
    except Exception as exc:
        logger.exception("Failed A2A call to %s (%s)", tool_name, target_url)
        return f"エラー: {cfg['fallback_name']} ({target_url}) との通信に失敗しました: {exc}"


async def process_main_task(user_input: str) -> str:
    """Orchestrate user queries across specialized subagents via OpenAI Tool Calling + A2A."""
    openai_tools = await discover_agents()
    openai_client = _get_openai_client()

    messages: list[dict[str, Any]] = [
        {
            "role": "system",
            "content": (
                "あなたはマルチエージェントシステムのメインオーケストレーターです。"
                "ユーザーからの問い合わせ内容を分析し、必要に応じて以下の専門サブエージェントをツールとして呼び出してください:\n"
                "- call_hr_agent: 従業員情報の照会、入社手続きなどのHR業務\n"
                "- call_it_agent: ノートPCなどIT機器の在庫照会、機器の割り当てなどのIT業務\n"
                "複数のドメインにまたがる依頼（例：従業員情報とIT機器の割り当てを同時に行う）の場合は、"
                "適切なサブエージェントを必要な数だけ（並列または順次）呼び出し、取得した結果を分かりやすく整理して日本語で回答してください。"
            ),
        },
        {"role": "user", "content": user_input},
    ]

    response = await openai_client.chat.completions.create(
        model=DEPLOYMENT_NAME,
        messages=messages,
        tools=openai_tools if openai_tools else None,
    )

    for _ in range(5):
        choice = response.choices[0]
        if choice.finish_reason != "tool_calls" or not choice.message.tool_calls:
            break

        messages.append(choice.message.model_dump(exclude_none=True))

        tool_calls = choice.message.tool_calls
        results = await asyncio.gather(
            *(
                _execute_tool_call(tc.function.name, tc.function.arguments or "{}")
                for tc in tool_calls
            )
        )

        for tc, result_text in zip(tool_calls, results):
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                }
            )

        response = await openai_client.chat.completions.create(
            model=DEPLOYMENT_NAME,
            messages=messages,
            tools=openai_tools if openai_tools else None,
        )

    return response.choices[0].message.content or ""
