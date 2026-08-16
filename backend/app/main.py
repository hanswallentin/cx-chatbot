import logging
from contextlib import asynccontextmanager

from anthropic import AsyncAnthropic
from fastapi import FastAPI
from pydantic import BaseModel

from app.config import (
    anthropic_api_key,
    feature_flags,
    guardrails_settings,
    llm_settings,
    log_level,
    mcp_server_url,
    policy_text,
)
from app.guardrails import GuardrailsClassifier
from app.mcp_client import MCPToolClient
from app.mock_llm import mock_create_message
from app.orchestrator import Orchestrator
from app.prompts import build_system_prompt
from app.session_store import InMemorySessionStore

logging.basicConfig(level=log_level())
logger = logging.getLogger(__name__)

app_state: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    llm = llm_settings()
    flags = feature_flags()
    api_key = anthropic_api_key()

    mcp_client = MCPToolClient(mcp_server_url())
    await mcp_client.connect()
    tool_schemas = await mcp_client.list_tool_schemas()

    if api_key:
        create_message = AsyncAnthropic(api_key=api_key).messages.create
    elif flags.get("allow_mock_llm_fallback", True):
        logger.warning("No ANTHROPIC_API_KEY resolved - running in mocked-LLM fallback mode.")
        create_message = mock_create_message
    else:
        raise RuntimeError("No ANTHROPIC_API_KEY configured and feature_flags.allow_mock_llm_fallback is false.")

    guardrails_cfg = guardrails_settings()
    guardrails = GuardrailsClassifier(
        create_message=create_message,
        model=llm["guardrail_model"],
        categories=guardrails_cfg["categories"],
        sensitivity=guardrails_cfg["sensitivity"],
        enabled=guardrails_cfg["enabled"] and flags.get("guardrails_enabled", True),
    )

    orchestrator = Orchestrator(
        create_message=create_message,
        mcp_client=mcp_client,
        guardrails=guardrails,
        session_store=InMemorySessionStore(),
        system_prompt=build_system_prompt(tool_schemas, policy_text()),
        tool_schemas=tool_schemas,
        model=llm["model"],
        block_message=guardrails_cfg["block_message"].strip(),
        max_tokens=llm["max_tokens"],
        max_tool_iterations=llm["max_tool_iterations"],
    )
    app_state["orchestrator"] = orchestrator
    app_state["mcp_client"] = mcp_client

    yield

    await mcp_client.close()


app = FastAPI(title="Bookly Support Backend", lifespan=lifespan)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(body: ChatRequest) -> ChatResponse:
    orchestrator: Orchestrator = app_state["orchestrator"]
    reply = await orchestrator.handle_message(body.session_id, body.message)
    return ChatResponse(reply=reply)
