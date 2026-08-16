"""Thin async wrappers around the Bookly REST API.

Each function returns a plain JSON-able dict shaped for the LLM to reason
over — never raises on an expected API error (404/400/403), and never
exposes SQL, table names, or raw route paths. These are the functions the
MCP tools in server.py delegate to; kept separate so they're easy to unit
test with a mocked HTTP layer.
"""
from typing import Optional

import httpx

from config import api_base_url


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=api_base_url(), timeout=10.0)


def _error_from_response(resp: httpx.Response) -> dict:
    try:
        detail = resp.json().get("detail", resp.text)
    except ValueError:
        detail = resp.text
    return {"error": detail, "status_code": resp.status_code}


async def search_books(query: str) -> dict:
    async with _client() as client:
        resp = await client.get("/books", params={"query": query})
    if resp.status_code != 200:
        return _error_from_response(resp)
    books = resp.json()
    return {"books": books, "count": len(books)}


async def get_customer(email: str) -> dict:
    async with _client() as client:
        resp = await client.get("/customers/by-email", params={"email": email})
    if resp.status_code != 200:
        return _error_from_response(resp)
    return {"customer": resp.json()}


async def find_customer_orders(customer_id: int) -> dict:
    async with _client() as client:
        resp = await client.get(f"/customers/{customer_id}/orders")
    if resp.status_code != 200:
        return _error_from_response(resp)
    orders = resp.json()
    return {"orders": orders, "count": len(orders)}


async def get_order_status(order_id: int, customer_id: int) -> dict:
    async with _client() as client:
        resp = await client.get(f"/orders/{order_id}")
    if resp.status_code != 200:
        return _error_from_response(resp)

    order = resp.json()
    if order["customer_id"] != customer_id:
        return {"error": "This order does not belong to that customer.", "status_code": 403}
    return {"order": order}


async def initiate_return(
    order_id: int,
    customer_id: int,
    reason: str,
    item_id: Optional[int] = None,
) -> dict:
    body = {"customer_id": customer_id, "reason": reason}
    if item_id is not None:
        body["item_id"] = item_id

    async with _client() as client:
        resp = await client.patch(f"/orders/{order_id}/return", json=body)
    if resp.status_code != 200:
        return _error_from_response(resp)
    return {"order": resp.json()}
