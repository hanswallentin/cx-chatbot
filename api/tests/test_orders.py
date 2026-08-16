def test_get_order_by_id(client):
    resp = client.get("/orders/1001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == 1
    assert body["status"] == "delivered"
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "The Midnight Library"


def test_get_order_unknown_id(client):
    resp = client.get("/orders/999999")
    assert resp.status_code == 404


def test_get_multi_item_order(client):
    resp = client.get("/orders/2001")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 2
    assert body["status"] == "delivered"


def test_list_customer_orders(client):
    resp = client.get("/customers/1/orders")
    assert resp.status_code == 200
    order_ids = {o["order_id"] for o in resp.json()}
    assert order_ids == {1001, 3001}


def test_list_orders_unknown_customer(client):
    resp = client.get("/customers/999/orders")
    assert resp.status_code == 404


def test_initiate_return_success(client):
    resp = client.patch(
        "/orders/1001/return",
        json={"customer_id": 1, "reason": "Changed my mind"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "return_requested"
    assert body["items"][0]["status"] == "return_requested"


def test_initiate_return_wrong_customer(client):
    resp = client.patch(
        "/orders/1001/return",
        json={"customer_id": 2, "reason": "Not mine"},
    )
    assert resp.status_code == 403


def test_initiate_return_not_returnable_state(client):
    resp = client.patch(
        "/orders/3001/return",
        json={"customer_id": 1, "reason": "Too soon"},
    )
    assert resp.status_code == 400


def test_initiate_return_unknown_order(client):
    resp = client.patch(
        "/orders/999999/return",
        json={"customer_id": 1, "reason": "Ghost order"},
    )
    assert resp.status_code == 404


def test_initiate_return_missing_reason(client):
    resp = client.patch(
        "/orders/1001/return",
        json={"customer_id": 1, "reason": ""},
    )
    assert resp.status_code == 422


def test_initiate_return_single_item_of_multi_item_order(client):
    order_before = client.get("/orders/2001").json()
    item_ids = [item["id"] for item in order_before["items"]]
    target_item_id = item_ids[0]
    other_item_id = item_ids[1]

    resp = client.patch(
        "/orders/2001/return",
        json={"customer_id": 2, "item_id": target_item_id, "reason": "Only wanted one back"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "mixed"

    statuses_by_id = {item["id"]: item["status"] for item in body["items"]}
    assert statuses_by_id[target_item_id] == "return_requested"
    assert statuses_by_id[other_item_id] == "delivered"


def test_initiate_return_unknown_item_id(client):
    resp = client.patch(
        "/orders/2001/return",
        json={"customer_id": 2, "item_id": 999999, "reason": "Bad item id"},
    )
    assert resp.status_code == 404
