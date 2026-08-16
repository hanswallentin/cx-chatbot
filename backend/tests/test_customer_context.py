"""Covers the identity-gate integration point: the frontend collects the
customer's name/email once, up front, and the backend should fold that into
the system prompt for the session so the agent doesn't ask for the email
again — see Orchestrator._system_prompt_for in app/orchestrator.py.
"""
import pytest

from tests.conftest import build_orchestrator
from tests.fakes import text_message


def _last_main_conversation_system(llm) -> str:
    """llm.calls includes both the guardrail classifier calls and the main
    conversation calls, interleaved — filter out the classifier ones."""
    main_calls = [c for c in llm.calls if "content safety classifier" not in c["system"]]
    return main_calls[-1]["system"]


@pytest.mark.asyncio
async def test_known_customer_identity_is_added_to_system_prompt():
    script = [text_message("Hi Hans! How can I help you today?")]
    orchestrator, llm, mcp = build_orchestrator(script, {})

    await orchestrator.handle_message(
        "s1", "Hello", customer_name="Hans Wallentin", customer_email="hans.wallentin@gmail.com"
    )

    sent_system = _last_main_conversation_system(llm)
    assert "Hans Wallentin" in sent_system
    assert "hans.wallentin@gmail.com" in sent_system
    assert "do not ask for their email again" in sent_system.lower()


@pytest.mark.asyncio
async def test_no_identity_leaves_system_prompt_unchanged():
    script = [text_message("Hi! How can I help you today?")]
    orchestrator, llm, mcp = build_orchestrator(script, {})

    await orchestrator.handle_message("s2", "Hello")

    sent_system = _last_main_conversation_system(llm)
    assert sent_system == orchestrator.system_prompt


@pytest.mark.asyncio
async def test_identity_note_does_not_leak_into_persisted_history():
    """The known-customer note is appended to the system prompt per-call
    only — it must never end up stored as a conversation history entry."""
    script = [text_message("Hi Hans! How can I help you today?")]
    orchestrator, llm, mcp = build_orchestrator(script, {})

    await orchestrator.handle_message(
        "s3", "Hello", customer_name="Hans Wallentin", customer_email="hans.wallentin@gmail.com"
    )

    history = orchestrator.session_store.get_history("s3")
    for entry in history:
        content = entry["content"]
        if isinstance(content, str):
            assert "do not ask for their email again" not in content.lower()
