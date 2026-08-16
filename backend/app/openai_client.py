"""Adapts an AsyncOpenAI client to the create_message contract that
app/orchestrator.py and app/guardrails.py expect (see app/llm_types.py).

This is the only place that knows about OpenAI's actual wire format
(chat.completions, function-calling tool_calls, one "tool"-role message per
result) — everything upstream of build_create_message() stays provider-
neutral, so swapping providers again only means writing a new adapter here.
"""
import json
from typing import Optional

from app.llm_types import LLMMessage, TextBlock, ToolUseBlock


def _tool_schemas_to_openai(tools: Optional[list[dict]]) -> Optional[list[dict]]:
    if not tools:
        return None
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"],
            },
        }
        for t in tools
    ]


def _assistant_blocks_to_openai_message(blocks: list) -> dict:
    text = "".join(b.text for b in blocks if getattr(b, "type", None) == "text") or None
    tool_calls = [
        {
            "id": b.id,
            "type": "function",
            "function": {"name": b.name, "arguments": json.dumps(b.input)},
        }
        for b in blocks
        if getattr(b, "type", None) == "tool_use"
    ]
    message: dict = {"role": "assistant", "content": text}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return message


def _tool_results_to_openai_messages(blocks: list[dict]) -> list[dict]:
    return [{"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]} for b in blocks]


def _history_to_openai_messages(system: str, history: list[dict]) -> list[dict]:
    openai_messages = [{"role": "system", "content": system}]
    for entry in history:
        role, content = entry["role"], entry["content"]
        if isinstance(content, str):
            openai_messages.append({"role": role, "content": content})
        elif role == "assistant":
            openai_messages.append(_assistant_blocks_to_openai_message(content))
        elif role == "user":
            openai_messages.extend(_tool_results_to_openai_messages(content))
        else:
            raise ValueError(f"Unexpected conversation history entry: role={role!r} content={content!r}")
    return openai_messages


def _openai_response_to_message(response) -> LLMMessage:
    choice = response.choices[0]
    message = choice.message

    blocks: list = []
    if message.content:
        blocks.append(TextBlock(text=message.content))

    tool_calls = getattr(message, "tool_calls", None) or []
    for call in tool_calls:
        blocks.append(
            ToolUseBlock(id=call.id, name=call.function.name, input=json.loads(call.function.arguments))
        )

    stop_reason = "tool_use" if tool_calls else "end_turn"
    return LLMMessage(content=blocks, stop_reason=stop_reason)


def build_create_message(client):
    """Returns an async create_message(*, model, max_tokens, system, messages, tools=None)
    callable backed by the given AsyncOpenAI client.
    """

    async def create_message(*, model, max_tokens, system, messages, tools=None):
        openai_messages = _history_to_openai_messages(system, messages)
        openai_tools = _tool_schemas_to_openai(tools)

        kwargs = {}
        if openai_tools:
            kwargs["tools"] = openai_tools
            kwargs["tool_choice"] = "auto"

        response = await client.chat.completions.create(
            model=model,
            max_completion_tokens=max_tokens,
            messages=openai_messages,
            **kwargs,
        )
        return _openai_response_to_message(response)

    return create_message
