"""Mocked-LLM fallback used only when no ANTHROPIC_API_KEY resolves at
startup (see config.yaml feature_flags.allow_mock_llm_fallback). Not used
by the automated test suite, which instead injects its own scripted fakes
to test real orchestrator/guardrail logic deterministically.
"""
from dataclasses import dataclass, field

MOCK_MODE_NOTICE = (
    "[mock mode] No ANTHROPIC_API_KEY is configured, so I can't have a real conversation right now. "
    "Add a key to .env and restart the backend to enable live responses."
)


@dataclass
class MockTextBlock:
    text: str
    type: str = "text"


@dataclass
class MockMessage:
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"


async def mock_create_message(*, model, max_tokens, system, messages, tools=None):
    if "content safety classifier" in system:
        text = (
            '{"blocked": false, "category": null, '
            '"reason": "mock mode: guardrails classifier not evaluated (no ANTHROPIC_API_KEY configured)"}'
        )
    else:
        text = MOCK_MODE_NOTICE
    return MockMessage(content=[MockTextBlock(text=text)])
