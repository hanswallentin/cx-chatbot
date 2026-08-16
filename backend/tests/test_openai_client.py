"""Tests for the OpenAI adapter (app/openai_client.py) — the one place that
translates between our provider-neutral internal contract (app/llm_types.py,
the same one the orchestrator/guardrails and ScriptedLLM fakes use) and
OpenAI's actual chat.completions wire format. A fake AsyncOpenAI-shaped
client stands in for the network call.
"""
import json
from types import SimpleNamespace

import pytest

from app.llm_types import LLMMessage, TextBlock, ToolUseBlock
from app.openai_client import build_create_message
from tests.fakes import SAMPLE_TOOL_SCHEMAS


def _fake_openai_response(content=None, tool_calls=None, finish_reason="stop"):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message, finish_reason=finish_reason)
    return SimpleNamespace(choices=[choice])


def _fake_tool_call(call_id, name, arguments: dict):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


class FakeAsyncOpenAI:
    """Records the exact kwargs chat.completions.create was called with and
    returns a pre-built canned response."""

    def __init__(self, response):
        self._response = response
        self.last_call_kwargs = None

        class _Completions:
            async def create(inner_self, **kwargs):
                self.last_call_kwargs = kwargs
                return self._response

        self.chat = SimpleNamespace(completions=_Completions())


@pytest.mark.asyncio
async def test_plain_text_reply_maps_to_end_turn():
    client = FakeAsyncOpenAI(_fake_openai_response(content="Our return window is 30 days.", finish_reason="stop"))
    create_message = build_create_message(client)

    result = await create_message(
        model="gpt-5.5", max_tokens=200, system="You are Bookly's support agent.",
        messages=[{"role": "user", "content": "What's your return policy?"}],
    )

    assert isinstance(result, LLMMessage)
    assert result.stop_reason == "end_turn"
    assert result.content == [TextBlock(text="Our return window is 30 days.")]


@pytest.mark.asyncio
async def test_tool_call_response_maps_to_tool_use_block():
    tool_call = _fake_tool_call("call_1", "get_order_status", {"order_id": 2001, "customer_id": 2})
    client = FakeAsyncOpenAI(_fake_openai_response(content=None, tool_calls=[tool_call], finish_reason="tool_calls"))
    create_message = build_create_message(client)

    result = await create_message(
        model="gpt-5.5", max_tokens=200, system="sys",
        messages=[{"role": "user", "content": "status of order 2001?"}],
        tools=SAMPLE_TOOL_SCHEMAS,
    )

    assert result.stop_reason == "tool_use"
    assert result.content == [ToolUseBlock(id="call_1", name="get_order_status", input={"order_id": 2001, "customer_id": 2})]


@pytest.mark.asyncio
async def test_tool_schemas_converted_to_openai_function_format():
    client = FakeAsyncOpenAI(_fake_openai_response(content="ok"))
    create_message = build_create_message(client)

    await create_message(
        model="gpt-5.5", max_tokens=200, system="sys",
        messages=[{"role": "user", "content": "hi"}],
        tools=SAMPLE_TOOL_SCHEMAS,
    )

    sent_tools = client.last_call_kwargs["tools"]
    assert sent_tools[0]["type"] == "function"
    assert sent_tools[0]["function"]["name"] == SAMPLE_TOOL_SCHEMAS[0]["name"]
    assert sent_tools[0]["function"]["parameters"] == SAMPLE_TOOL_SCHEMAS[0]["input_schema"]
    assert client.last_call_kwargs["tool_choice"] == "auto"


@pytest.mark.asyncio
async def test_no_tools_omits_tools_kwarg():
    client = FakeAsyncOpenAI(_fake_openai_response(content="ok"))
    create_message = build_create_message(client)

    await create_message(model="gpt-5.4-mini", max_tokens=200, system="sys", messages=[{"role": "user", "content": "hi"}])

    assert "tools" not in client.last_call_kwargs
    assert "tool_choice" not in client.last_call_kwargs


@pytest.mark.asyncio
async def test_system_prompt_and_max_tokens_forwarded():
    client = FakeAsyncOpenAI(_fake_openai_response(content="ok"))
    create_message = build_create_message(client)

    await create_message(model="gpt-5.5", max_tokens=321, system="be helpful", messages=[{"role": "user", "content": "hi"}])

    assert client.last_call_kwargs["model"] == "gpt-5.5"
    assert client.last_call_kwargs["max_completion_tokens"] == 321
    assert client.last_call_kwargs["messages"][0] == {"role": "system", "content": "be helpful"}
    assert client.last_call_kwargs["messages"][1] == {"role": "user", "content": "hi"}


@pytest.mark.asyncio
async def test_assistant_tool_use_history_entry_converts_to_tool_calls_message():
    client = FakeAsyncOpenAI(_fake_openai_response(content="done"))
    create_message = build_create_message(client)

    history = [
        {"role": "user", "content": "return order 1001"},
        {
            "role": "assistant",
            "content": [ToolUseBlock(id="call_9", name="initiate_return", input={"order_id": 1001})],
        },
        {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": "call_9", "content": '{"order": {"status": "return_requested"}}'}],
        },
    ]

    await create_message(model="gpt-5.5", max_tokens=200, system="sys", messages=history)

    sent = client.last_call_kwargs["messages"]
    # system + user + assistant(tool_calls) + tool
    assert sent[2] == {"role": "assistant", "content": None, "tool_calls": [
        {"id": "call_9", "type": "function", "function": {"name": "initiate_return", "arguments": '{"order_id": 1001}'}}
    ]}
    assert sent[3] == {"role": "tool", "tool_call_id": "call_9", "content": '{"order": {"status": "return_requested"}}'}


@pytest.mark.asyncio
async def test_multiple_tool_results_in_one_history_entry_expand_to_separate_tool_messages():
    client = FakeAsyncOpenAI(_fake_openai_response(content="done"))
    create_message = build_create_message(client)

    history = [
        {
            "role": "assistant",
            "content": [
                ToolUseBlock(id="call_a", name="get_customer", input={"email": "x@example.com"}),
                ToolUseBlock(id="call_b", name="search_books", input={"query": "hail mary"}),
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "call_a", "content": '{"customer": {}}'},
                {"type": "tool_result", "tool_use_id": "call_b", "content": '{"books": []}'},
            ],
        },
    ]

    await create_message(model="gpt-5.5", max_tokens=200, system="sys", messages=history)

    sent = client.last_call_kwargs["messages"]
    tool_messages = [m for m in sent if m.get("role") == "tool"]
    assert tool_messages == [
        {"role": "tool", "tool_call_id": "call_a", "content": '{"customer": {}}'},
        {"role": "tool", "tool_call_id": "call_b", "content": '{"books": []}'},
    ]
