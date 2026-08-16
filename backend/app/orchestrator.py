"""The conversation loop: guardrail the input, run the LLM tool-use loop
against the MCP-backed tools, guardrail the output, persist history.

`create_message` and `mcp_client` are both injected so this class never
constructs a real LLM/MCP connection itself — that happens once at app
startup in main.py, where create_message is backed by the OpenAI adapter
(app/openai_client.py) or the mocked fallback (app/mock_llm.py). Tests
construct an Orchestrator directly with fakes satisfying the same two
small interfaces, so scripted conversations run without any network access.
"""
import json
import logging
from typing import Any, Optional, Protocol

from app.guardrails import GuardrailsClassifier, log_blocked_event

logger = logging.getLogger(__name__)


class SupportsToolClient(Protocol):
    async def list_tool_schemas(self) -> list[dict[str, Any]]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...


class Orchestrator:
    def __init__(
        self,
        create_message,
        mcp_client: SupportsToolClient,
        guardrails: GuardrailsClassifier,
        session_store,
        system_prompt: str,
        tool_schemas: list[dict[str, Any]],
        model: str,
        block_message: str,
        max_tokens: int = 1024,
        max_tool_iterations: int = 5,
    ):
        self._create_message = create_message
        self.mcp_client = mcp_client
        self.guardrails = guardrails
        self.session_store = session_store
        self.system_prompt = system_prompt
        self.model = model
        self.block_message = block_message
        self.max_tokens = max_tokens
        self.max_tool_iterations = max_tool_iterations
        self.tools = [
            {
                "name": t["name"],
                "description": t["description"],
                "input_schema": t["input_schema"],
            }
            for t in tool_schemas
        ]

    async def handle_message(
        self,
        session_id: str,
        user_text: str,
        customer_name: Optional[str] = None,
        customer_email: Optional[str] = None,
    ) -> str:
        input_verdict = await self.guardrails.classify(user_text)
        if input_verdict.blocked:
            log_blocked_event("input", input_verdict)
            return self.guardrails_block_message()

        history = list(self.session_store.get_history(session_id))
        history.append({"role": "user", "content": user_text})

        system_prompt = self._system_prompt_for(customer_name, customer_email)
        reply_text = await self._run_tool_loop(history, system_prompt)

        output_verdict = await self.guardrails.classify(reply_text)
        if output_verdict.blocked:
            log_blocked_event("output", output_verdict)
            reply_text = self.guardrails_block_message()
            # Don't persist a blocked model output into history as if it were said.
            history.append({"role": "assistant", "content": reply_text})
            self.session_store.save_history(session_id, history)
            return reply_text

        history.append({"role": "assistant", "content": reply_text})
        self.session_store.save_history(session_id, history)
        return reply_text

    def guardrails_block_message(self) -> str:
        return self.block_message

    def _system_prompt_for(self, customer_name: Optional[str], customer_email: Optional[str]) -> str:
        """The frontend collects the customer's name/email once, up front, via
        its own identity form — so the agent shouldn't re-ask for an email it
        already has. This appends a short known-customer note to the system
        prompt for this call only; it never touches persisted history.
        """
        if not customer_name and not customer_email:
            return self.system_prompt
        return (
            f"{self.system_prompt}\n\n"
            f"The customer chatting with you has already provided their name and email "
            f"at the start of this session — do not ask for their email again. "
            f'Known customer: name="{customer_name or "unknown"}", email="{customer_email or "unknown"}".'
        )

    async def _run_tool_loop(self, history: list[dict[str, Any]], system_prompt: str) -> str:
        for _ in range(self.max_tool_iterations):
            response = await self._create_message(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt,
                messages=history,
                tools=self.tools,
            )

            if response.stop_reason != "tool_use":
                return self._extract_text(response)

            history.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in response.content:
                if getattr(block, "type", None) != "tool_use":
                    continue
                result = await self.mcp_client.call_tool(block.name, block.input)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result),
                    }
                )
            history.append({"role": "user", "content": tool_results})

        logger.warning("Tool loop exceeded max_tool_iterations=%d without a final reply", self.max_tool_iterations)
        return "Sorry, I'm having trouble completing that. Could you rephrase, or try again in a moment?"

    @staticmethod
    def _extract_text(response) -> str:
        return "".join(block.text for block in response.content if getattr(block, "type", None) == "text").strip()
