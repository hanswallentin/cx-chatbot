"""Bookly REST API. The only layer allowed to touch the database directly.

Owns all validation: does an order belong to this customer, is it in a
returnable state, etc. The MCP server calls this over HTTP — it never talks
to sqlite itself.
"""
import sqlite3

from fastapi import Depends, FastAPI, HTTPException, Query

from app.db import get_db
from app.models import Book, Customer, Order, OrderLineItem, ReturnRequest

app = FastAPI(title="Bookly API")

RETURNABLE_STATUSES = {"delivered"}


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/customers/by-email", response_model=Customer)
def get_customer_by_email(email: str = Query(...), db: sqlite3.Connection = Depends(get_db)) -> Customer:
    row = db.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No customer found with email {email}")
    return Customer(**dict(row))


@app.get("/customers/{customer_id}", response_model=Customer)
def get_customer(customer_id: int, db: sqlite3.Connection = Depends(get_db)) -> Customer:
    row = db.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No customer found with id {customer_id}")
    return Customer(**dict(row))


@app.get("/books", response_model=list[Book])
def search_books(query: str = Query(..., min_length=1), db: sqlite3.Connection = Depends(get_db)) -> list[Book]:
    like = f"%{query}%"
    rows = db.execute(
        "SELECT * FROM books WHERE title LIKE ? OR author LIKE ? ORDER BY title",
        (like, like),
    ).fetchall()
    return [Book(**dict(r)) for r in rows]


@app.get("/books/{book_id}", response_model=Book)
def get_book(book_id: int, db: sqlite3.Connection = Depends(get_db)) -> Book:
    row = db.execute("SELECT * FROM books WHERE book_id = ?", (book_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"No book found with id {book_id}")
    return Book(**dict(row))


def _load_order(db: sqlite3.Connection, order_id: int) -> Order:
    rows = db.execute(
        """
        SELECT orders.*, books.title AS title
        FROM orders JOIN books ON books.book_id = orders.book_id
        WHERE orders.order_id = ?
        ORDER BY orders.id
        """,
        (order_id,),
    ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No order found with id {order_id}")

    items = [OrderLineItem(**dict(r)) for r in rows]
    statuses = {item.status for item in items}
    overall_status = statuses.pop() if len(statuses) == 1 else "mixed"
    return Order(order_id=order_id, customer_id=items[0].customer_id, status=overall_status, items=items)


@app.get("/orders/{order_id}", response_model=Order)
def get_order(order_id: int, db: sqlite3.Connection = Depends(get_db)) -> Order:
    return _load_order(db, order_id)


@app.get("/customers/{customer_id}/orders", response_model=list[Order])
def list_customer_orders(customer_id: int, db: sqlite3.Connection = Depends(get_db)) -> list[Order]:
    customer_row = db.execute("SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    if customer_row is None:
        raise HTTPException(status_code=404, detail=f"No customer found with id {customer_id}")

    order_ids = [
        r["order_id"]
        for r in db.execute(
            "SELECT DISTINCT order_id FROM orders WHERE customer_id = ? ORDER BY order_id",
            (customer_id,),
        ).fetchall()
    ]
    return [_load_order(db, oid) for oid in order_ids]


@app.patch("/orders/{order_id}/return", response_model=Order)
def initiate_return(order_id: int, body: ReturnRequest, db: sqlite3.Connection = Depends(get_db)) -> Order:
    order = _load_order(db, order_id)

    if order.customer_id != body.customer_id:
        raise HTTPException(status_code=403, detail="This order does not belong to that customer.")

    if body.item_id is not None:
        targets = [item for item in order.items if item.id == body.item_id]
        if not targets:
            raise HTTPException(status_code=404, detail=f"No line item {body.item_id} on order {order_id}.")
    else:
        targets = order.items

    not_returnable = [item for item in targets if item.status not in RETURNABLE_STATUSES]
    if not_returnable:
        bad_statuses = ", ".join(sorted({item.status for item in not_returnable}))
        raise HTTPException(
            status_code=400,
            detail=f"Order {order_id} is not in a returnable state (status: {bad_statuses}).",
        )

    target_ids = [item.id for item in targets]
    db.executemany(
        "UPDATE orders SET status = 'return_requested' WHERE id = ?",
        [(tid,) for tid in target_ids],
    )
    db.commit()

    return _load_order(db, order_id)
