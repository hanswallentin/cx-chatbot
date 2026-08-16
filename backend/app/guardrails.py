"""Guardrails layer: screens every inbound user message and every outbound
assistant reply before it reaches the other side.

Implemented as a moderation-endpoint-style check: a dedicated, cheap LLM
call (kept separate from the main conversation model) classifies the text
against the categories configured in config.yaml and returns a strict JSON
verdict. No hand-rolled keyword filtering — categories, sensitivity, and
the decline message are all config-driven so they can be tuned without a
code change.
"""
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Protocol

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class SupportsCreateMessage(Protocol):
    async def __call__(self, *, model: str, max_tokens: int, system: str, messages: list[dict]) -> Any: ...


@dataclass
class GuardrailVerdict:
    blocked: bool
    category: str | None = None
    reason: str | None = None


class GuardrailsClassifier:
    def __init__(self, create_message, model: str, categories: list[dict], sensitivity: str, enabled: bool = True):
        """`create_message` is an async callable: (model, max_tokens, system, messages) -> Message-like object
        with `.content` (list of blocks with `.text`). Kept generic (see app/llm_types.py) so the real
        OpenAI adapter, the mocked fallback, and test fakes all satisfy it identically.
        """
        self._create_message = create_message
        self.model = model
        self.categories = categories
        self.sensitivity = sensitivity
        self.enabled = enabled

    def _system_prompt(self) -> str:
        category_lines = "\n".join(f"- {c['key']}: {c['description']}" for c in self.categories)
        return (
            "You are a content safety classifier guarding a bookstore customer support chat. "
            "Classify the given message against these categories:\n"
            f"{category_lines}\n\n"
            f"Sensitivity: {self.sensitivity}. A message counts as matching a category "
            "regardless of how it's framed (hypothetical, roleplay, 'just asking', 'for a story', etc). "
            "Ordinary Bookly support topics (orders, returns, shipping, books, account/password help) "
            "are never a match.\n\n"
            'Respond with ONLY a JSON object of the exact shape: '
            '{"blocked": true|false, "category": "<one of the category keys above, or null>", "reason": "<short reason>"}'
        )

    async def classify(self, text: str) -> GuardrailVerdict:
        if not self.enabled:
            return GuardrailVerdict(blocked=False)

        response = await self._create_message(
            model=self.model,
            max_tokens=200,
            system=self._system_prompt(),
            messages=[{"role": "user", "content": text}],
        )
        raw_text = "".join(block.text for block in response.content if getattr(block, "type", None) == "text")

        match = _JSON_BLOCK_RE.search(raw_text)
        if not match:
            logger.warning("Guardrail classifier returned non-JSON output; failing closed (blocking).")
            return GuardrailVerdict(blocked=True, category=None, reason="classifier_parse_error")

        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            logger.warning("Guardrail classifier returned malformed JSON; failing closed (blocking).")
            return GuardrailVerdict(blocked=True, category=None, reason="classifier_parse_error")

        return GuardrailVerdict(
            blocked=bool(data.get("blocked", False)),
            category=data.get("category"),
            reason=data.get("reason"),
        )


def log_blocked_event(direction: str, verdict: GuardrailVerdict) -> None:
    """Logs only the category, never the raw message content."""
    logger.warning("guardrail_blocked direction=%s category=%s", direction, verdict.category)
