import respx
from httpx import Response

import bookly_client


@respx.mock
async def test_search_books_passes_query_and_shapes_result(api_base):
    route = respx.get(f"{api_base}/books", params={"query": "Weir"}).mock(
        return_value=Response(200, json=[{"book_id": 2, "title": "Project Hail Mary"}])
    )
    result = await bookly_client.search_books("Weir")
    assert route.called
    assert result["count"] == 1
    assert result["books"][0]["title"] == "Project Hail Mary"


@respx.mock
async def test_search_books_no_results(api_base):
    respx.get(f"{api_base}/books", params={"query": "zzz"}).mock(return_value=Response(200, json=[]))
    result = await bookly_client.search_books("zzz")
    assert result == {"books": [], "count": 0}


@respx.mock
async def test_get_customer_found(api_base):
    respx.get(f"{api_base}/customers/by-email", params={"email": "priya.patel@example.com"}).mock(
        return_value=Response(200, json={"customer_id": 1, "name": "Priya Patel", "email": "priya.patel@example.com", "created_at": "2025-11-02"})
    )
    result = await bookly_client.get_customer("priya.patel@example.com")
    assert result["customer"]["customer_id"] == 1


@respx.mock
async def test_get_customer_not_found_shapes_error(api_base):
    respx.get(f"{api_base}/customers/by-email", params={"email": "nobody@example.com"}).mock(
        return_value=Response(404, json={"detail": "No customer found with email nobody@example.com"})
    )
    result = await bookly_client.get_customer("nobody@example.com")
    assert "error" in result
    assert result["status_code"] == 404


@respx.mock
async def test_find_customer_orders(api_base):
    respx.get(f"{api_base}/customers/1/orders").mock(
        return_value=Response(200, json=[{"order_id": 1001, "customer_id": 1, "status": "delivered", "items": []}])
    )
    result = await bookly_client.find_customer_orders(1)
    assert result["count"] == 1
    assert result["orders"][0]["order_id"] == 1001


@respx.mock
async def test_get_order_status_ok(api_base):
    respx.get(f"{api_base}/orders/1001").mock(
        return_value=Response(200, json={"order_id": 1001, "customer_id": 1, "status": "delivered", "items": []})
    )
    result = await bookly_client.get_order_status(1001, customer_id=1)
    assert result["order"]["status"] == "delivered"


@respx.mock
async def test_get_order_status_wrong_customer_is_rejected_before_leaking_data(api_base):
    respx.get(f"{api_base}/orders/1001").mock(
        return_value=Response(200, json={"order_id": 1001, "customer_id": 1, "status": "delivered", "items": []})
    )
    result = await bookly_client.get_order_status(1001, customer_id=999)
    assert result["error"]
    assert result["status_code"] == 403


@respx.mock
async def test_get_order_status_unknown_order(api_base):
    respx.get(f"{api_base}/orders/999999").mock(return_value=Response(404, json={"detail": "No order found with id 999999"}))
    result = await bookly_client.get_order_status(999999, customer_id=1)
    assert result["status_code"] == 404


@respx.mock
async def test_initiate_return_success(api_base):
    route = respx.patch(f"{api_base}/orders/1001/return").mock(
        return_value=Response(200, json={"order_id": 1001, "customer_id": 1, "status": "return_requested", "items": []})
    )
    result = await bookly_client.initiate_return(1001, customer_id=1, reason="Changed my mind")
    assert route.called
    sent_body = route.calls.last.request.content
    assert b"Changed my mind" in sent_body
    assert result["order"]["status"] == "return_requested"


@respx.mock
async def test_initiate_return_with_item_id_passes_it_through(api_base):
    route = respx.patch(f"{api_base}/orders/2001/return").mock(
        return_value=Response(200, json={"order_id": 2001, "customer_id": 2, "status": "mixed", "items": []})
    )
    await bookly_client.initiate_return(2001, customer_id=2, reason="Only one item", item_id=5)
    sent_body = route.calls.last.request.content
    assert b'"item_id":5' in sent_body


@respx.mock
async def test_initiate_return_not_returnable_shapes_error(api_base):
    respx.patch(f"{api_base}/orders/3001/return").mock(
        return_value=Response(400, json={"detail": "Order 3001 is not in a returnable state (status: placed)."})
    )
    result = await bookly_client.initiate_return(3001, customer_id=1, reason="Too soon")
    assert result["status_code"] == 400
    assert "not in a returnable state" in result["error"]
