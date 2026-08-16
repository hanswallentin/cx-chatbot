def test_search_books_by_title(client):
    resp = client.get("/books", params={"query": "Midnight"})
    assert resp.status_code == 200
    titles = [b["title"] for b in resp.json()]
    assert "The Midnight Library" in titles


def test_search_books_by_author(client):
    resp = client.get("/books", params={"query": "Weir"})
    assert resp.status_code == 200
    titles = [b["title"] for b in resp.json()]
    assert titles == ["Project Hail Mary"]


def test_search_books_no_match(client):
    resp = client.get("/books", params={"query": "Nonexistent Book Title Zzz"})
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_book_by_id(client):
    resp = client.get("/books/1")
    assert resp.status_code == 200
    assert resp.json()["title"] == "The Midnight Library"


def test_get_book_unknown_id(client):
    resp = client.get("/books/999")
    assert resp.status_code == 404
