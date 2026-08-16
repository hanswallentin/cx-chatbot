import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.guardrails import GuardrailsClassifier
from app.orchestrator import Orchestrator
from app.session_store import InMemorySessionStore
from tests.fakes import SAMPLE_TOOL_SCHEMAS, FakeMCPClient, ScriptedLLM

DEFAULT_CATEGORIES = [
    {"key": "hate_speech", "description": "Hate speech or slurs."},
    {"key": "violence", "description": "Graphic violence or threats."},
    {"key": "sexual_content", "description": "Sexual or explicit content."},
    {"key": "drugs", "description": "Illegal drug instructions."},
    {"key": "off_topic", "description": "Anything unrelated to Bookly bookstore support."},
]

BLOCK_MESSAGE = (
    "I'm not able to help with that here. I can help with Bookly orders, "
    "returns, book questions, or your account — is there something along those lines I can help with?"
)


def build_orchestrator(
    conversation_script,
    tool_responses=None,
    guardrail_verdict='{"blocked": false, "category": null, "reason": "clean"}',
    guardrails_enabled=True,
):
    llm = ScriptedLLM(conversation_script, guardrail_verdict=guardrail_verdict)
    mcp_client = FakeMCPClient(tool_responses)
    guardrails = GuardrailsClassifier(
        create_message=llm,
        model="gpt-5.4-mini",
        categories=DEFAULT_CATEGORIES,
        sensitivity="strict",
        enabled=guardrails_enabled,
    )
    orchestrator = Orchestrator(
        create_message=llm,
        mcp_client=mcp_client,
        guardrails=guardrails,
        session_store=InMemorySessionStore(),
        system_prompt="You are Bookly's customer support agent.",
        tool_schemas=SAMPLE_TOOL_SCHEMAS,
        model="gpt-5.5",
        block_message=BLOCK_MESSAGE,
        max_tokens=1024,
        max_tool_iterations=5,
    )
    return orchestrator, llm, mcp_client
