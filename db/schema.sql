-- Bookly schema. SQLite. Three tables only, per spec.

CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    email       TEXT NOT NULL UNIQUE,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS books (
    book_id     INTEGER PRIMARY KEY,
    title       TEXT NOT NULL,
    author      TEXT NOT NULL,
    isbn        TEXT NOT NULL,
    price       REAL NOT NULL,
    stock_qty   INTEGER NOT NULL
);

-- One row per line item. `order_id` is the customer-facing order number and
-- is intentionally NOT unique here: a multi-item order shares one order_id
-- across several rows. `id` is the surrogate row key used to target a
-- single line item (e.g. for a partial return on a multi-item order).
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id        INTEGER NOT NULL,
    customer_id     INTEGER NOT NULL REFERENCES customers(customer_id),
    book_id         INTEGER NOT NULL REFERENCES books(book_id),
    quantity        INTEGER NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('placed', 'shipped', 'delivered', 'return_requested', 'refunded')),
    order_date      TEXT NOT NULL,
    tracking_number TEXT
);

CREATE INDEX IF NOT EXISTS idx_orders_order_id ON orders(order_id);
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
