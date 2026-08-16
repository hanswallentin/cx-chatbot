"""Real MCP client: connects to the Bookly MCP server over streamable-http
and exposes the two operations the orchestrator needs. Kept as a small,
duck-type-compatible interface (list_tool_schemas / call_tool) so tests can
swap in a fake without touching the network.
"""
import json
import logging
from contextlib import AsyncExitStack
from typing import Any, Optional

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

logger = logging.getLogger(__name__)


class MCPToolClient:
    def __init__(self, url: str):
        self.url = url
        self._session: Optional[ClientSession] = None
        self._stack: Optional[AsyncExitStack] = None

    async def connect(self) -> None:
        self._stack = AsyncExitStack()
        read, write, _ = await self._stack.enter_async_context(streamablehttp_client(self.url))
        self._session = await self._stack.enter_async_context(ClientSession(read, write))
        await self._session.initialize()
        logger.info("Connected to MCP server at %s", self.url)

    async def close(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()

    async def list_tool_schemas(self) -> list[dict[str, Any]]:
        result = await self._session.list_tools()
        return [
            {
                "name": tool.name,
                "description": tool.description or "",
                "input_schema": tool.inputSchema,
            }
            for tool in result.tools
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await self._session.call_tool(name, arguments)
        texts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
        payload = texts[0] if texts else "{}"
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        if result.isError and "error" not in parsed:
            parsed = {"error": payload}
        return parsed
