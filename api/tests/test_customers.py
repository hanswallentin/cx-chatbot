def test_get_customer_by_id(client):
    resp = client.get("/customers/1")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Priya Patel"
    assert body["email"] == "priya.patel@example.com"


def test_get_customer_unknown_id(client):
    resp = client.get("/customers/999")
    assert resp.status_code == 404


def test_get_customer_by_email(client):
    resp = client.get("/customers/by-email", params={"email": "marcus.chen@example.com"})
    assert resp.status_code == 200
    assert resp.json()["customer_id"] == 2


def test_get_customer_by_email_unknown(client):
    resp = client.get("/customers/by-email", params={"email": "nobody@example.com"})
    assert resp.status_code == 404
