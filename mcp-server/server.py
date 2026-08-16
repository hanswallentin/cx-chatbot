"""Bookly MCP server. Wraps the REST API as MCP tools scoped around what a
support agent actually needs to do — the LLM only ever sees these tool
names, arguments, and structured results, never SQL or raw API routes.
"""
from typing import Optional

from mcp.server.fastmcp import FastMCP

import bookly_client
from config import mcp_settings, tool_descriptions

settings = mcp_settings()
descriptions = tool_descriptions()

mcp = FastMCP("bookly-support")
mcp.settings.host = "0.0.0.0"
mcp.settings.port = settings["port"]
mcp.settings.streamable_http_path = settings["mcp_path"]


@mcp.tool(name="search_books", description=descriptions["search_books"])
async def search_books(query: str) -> dict:
    return await bookly_client.search_books(query)


@mcp.tool(name="get_customer", description=descriptions["get_customer"])
async def get_customer(email: str) -> dict:
    return await bookly_client.get_customer(email)


@mcp.tool(name="find_customer_orders", description=descriptions["find_customer_orders"])
async def find_customer_orders(customer_id: int) -> dict:
    return await bookly_client.find_customer_orders(customer_id)


@mcp.tool(name="get_order_status", description=descriptions["get_order_status"])
async def get_order_status(order_id: int, customer_id: int) -> dict:
    return await bookly_client.get_order_status(order_id, customer_id)


@mcp.tool(name="initiate_return", description=descriptions["initiate_return"])
async def initiate_return(order_id: int, customer_id: int, reason: str, item_id: Optional[int] = None) -> dict:
    return await bookly_client.initiate_return(order_id, customer_id, reason, item_id)


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
