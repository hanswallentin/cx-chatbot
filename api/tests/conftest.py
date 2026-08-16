import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.db import get_db_path
from app.main import app

SCHEMA_PATH = Path(__file__).parents[2] / "db" / "schema.sql"


@pytest.fixture
def db_path(tmp_path) -> str:
    path = str(tmp_path / "test_bookly.db")
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_PATH.read_text())

    conn.executemany(
        "INSERT INTO customers (customer_id, name, email, created_at) VALUES (?, ?, ?, ?)",
        [
            (1, "Priya Patel", "priya.patel@example.com", "2025-11-02"),
            (2, "Marcus Chen", "marcus.chen@example.com", "2025-12-14"),
        ],
    )
    conn.executemany(
        "INSERT INTO books (book_id, title, author, isbn, price, stock_qty) VALUES (?, ?, ?, ?, ?, ?)",
        [
            (1, "The Midnight Library", "Matt Haig", "9780525559474", 16.99, 42),
            (2, "Project Hail Mary", "Andy Weir", "9780593135204", 18.99, 30),
        ],
    )
    conn.executemany(
        "INSERT INTO orders (order_id, customer_id, book_id, quantity, status, order_date, tracking_number) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            # single-item, delivered -> returnable
            (1001, 1, 1, 1, "delivered", "2026-07-20", "TRACK1"),
            # multi-item order, both delivered -> returnable, used for item_id targeting
            (2001, 2, 1, 1, "delivered", "2026-07-25", "TRACK2"),
            (2001, 2, 2, 2, "delivered", "2026-07-25", "TRACK2"),
            # placed, not yet returnable
            (3001, 1, 2, 1, "placed", "2026-08-10", None),
        ],
    )
    conn.commit()
    conn.close()
    return path


@pytest.fixture
def client(db_path) -> TestClient:
    app.dependency_overrides[get_db_path] = lambda: db_path
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
