"""The orchestrator's provider-neutral view of a model turn.

Both the OpenAI adapter (app/openai_client.py) and the mocked-fallback
(app/mock_llm.py) produce these same shapes, so app/orchestrator.py and
app/guardrails.py never need to know which LLM provider is actually behind
`create_message` — they only depend on this contract.
"""
from dataclasses import dataclass, field


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class LLMMessage:
    content: list = field(default_factory=list)
    # "tool_use" if the model wants to call one or more tools, "end_turn" otherwise.
    stop_reason: str = "end_turn"
