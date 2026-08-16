"""Mocked-LLM fallback used only when no LLM API key resolves at startup
(see config.yaml feature_flags.allow_mock_llm_fallback). Not used by the
automated test suite, which instead injects its own scripted fakes to test
real orchestrator/guardrail logic deterministically.
"""
from app.llm_types import LLMMessage, TextBlock

MOCK_MODE_NOTICE = (
    "[mock mode] No LLM API key is configured, so I can't have a real conversation right now. "
    "Add a key to .env and restart the backend to enable live responses."
)


async def mock_create_message(*, model, max_tokens, system, messages, tools=None):
    if "content safety classifier" in system:
        text = (
            '{"blocked": false, "category": null, '
            '"reason": "mock mode: guardrails classifier not evaluated (no LLM API key configured)"}'
        )
    else:
        text = MOCK_MODE_NOTICE
    return LLMMessage(content=[TextBlock(text=text)])
