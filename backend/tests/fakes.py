"""Test doubles for the Anthropic client and the MCP tool client.

Neither fake talks to a network. ScriptedAnthropic plays back a
pre-written sequence of model turns so conversation tests are fully
deterministic; FakeMCPClient records every tool invocation so tests can
assert on exactly what was (or wasn't) called.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Union

SAMPLE_TOOL_SCHEMAS = [
    {"name": "search_books", "description": "Search the catalog.", "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}},
    {"name": "get_customer", "description": "Look up a customer by email.", "input_schema": {"type": "object", "properties": {"email": {"type": "string"}}}},
    {"name": "find_customer_orders", "description": "List a customer's orders.", "input_schema": {"type": "object", "properties": {"customer_id": {"type": "integer"}}}},
    {"name": "get_order_status", "description": "Get an order's status.", "input_schema": {"type": "object", "properties": {"order_id": {"type": "integer"}, "customer_id": {"type": "integer"}}}},
    {"name": "initiate_return", "description": "Start a return.", "input_schema": {"type": "object", "properties": {"order_id": {"type": "integer"}, "customer_id": {"type": "integer"}, "item_id": {"type": "integer"}, "reason": {"type": "string"}}}},
]


@dataclass
class FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class FakeToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class FakeMessage:
    content: list
    stop_reason: str = "end_turn"


def text_message(text: str) -> FakeMessage:
    return FakeMessage(content=[FakeTextBlock(text=text)], stop_reason="end_turn")


def tool_use_message(tool_use_id: str, name: str, tool_input: dict) -> FakeMessage:
    return FakeMessage(content=[FakeToolUseBlock(id=tool_use_id, name=name, input=tool_input)], stop_reason="tool_use")


class ScriptedAnthropic:
    """One create_message callable used for BOTH the main conversation and
    the guardrails classifier, matching how the real app wires a single
    Anthropic client to both roles (see backend/app/main.py). Routes on the
    system prompt: guardrail calls (system mentions "content safety
    classifier") get a fixed verdict; everything else pops the next
    scripted turn off the conversation queue.
    """

    def __init__(
        self,
        conversation_script: list[FakeMessage],
        guardrail_verdict: str = '{"blocked": false, "category": null, "reason": "clean"}',
    ):
        self._script = list(conversation_script)
        self.guardrail_verdict = guardrail_verdict
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, *, model, max_tokens, system, messages, tools=None):
        self.calls.append({"model": model, "system": system, "messages": messages, "tools": tools})
        if "content safety classifier" in system:
            return text_message(self.guardrail_verdict)
        if not self._script:
            raise AssertionError("ScriptedAnthropic ran out of scripted conversation turns")
        return self._script.pop(0)


class FakeMCPClient:
    def __init__(self, tool_responses: Optional[dict[str, Union[dict, Callable[[dict], dict]]]] = None):
        self.tool_responses = tool_responses or {}
        self.calls: list[tuple[str, dict]] = []

    async def list_tool_schemas(self) -> list[dict]:
        return SAMPLE_TOOL_SCHEMAS

    async def call_tool(self, name: str, arguments: dict) -> dict:
        self.calls.append((name, dict(arguments)))
        handler = self.tool_responses.get(name)
        if handler is None:
            return {"error": f"no fake handler registered for tool {name}"}
        return handler(arguments) if callable(handler) else handler
