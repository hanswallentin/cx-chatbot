"""Create (or reset) the Bookly SQLite database and seed it from config.yaml.

Run with no arguments; reads DATABASE_PATH env var (falls back to the value
in config.yaml -> database.default_path) and CONFIG_PATH (defaults to
/config.yaml, which docker-compose mounts read-only into this container).
"""
import os
import sqlite3
import sys
from pathlib import Path

import yaml

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/config.yaml")
SCHEMA_PATH = os.environ.get("SCHEMA_PATH", str(Path(__file__).parent / "schema.sql"))


def load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return yaml.safe_load(f)


def resolve_db_path(config: dict) -> str:
    env_name = config["database"]["path_env"]
    return os.environ.get(env_name) or config["database"]["default_path"]


def seed(config: dict, db_path: str) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    # Fresh DB every seed run — this is a prototype reset script, not a migration tool.
    if Path(db_path).exists():
        Path(db_path).unlink()

    conn = sqlite3.connect(db_path)
    try:
        with open(SCHEMA_PATH) as f:
            conn.executescript(f.read())

        seed_data = config["seed"]

        conn.executemany(
            "INSERT INTO customers (customer_id, name, email, created_at) VALUES (:customer_id, :name, :email, :created_at)",
            seed_data["customers"],
        )
        conn.executemany(
            "INSERT INTO books (book_id, title, author, isbn, price, stock_qty) VALUES (:book_id, :title, :author, :isbn, :price, :stock_qty)",
            seed_data["books"],
        )
        conn.executemany(
            "INSERT INTO orders (order_id, customer_id, book_id, quantity, status, order_date, tracking_number) "
            "VALUES (:order_id, :customer_id, :book_id, :quantity, :status, :order_date, :tracking_number)",
            seed_data["orders"],
        )
        conn.commit()

        n_customers = conn.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        n_books = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        n_orders = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        print(f"Seeded {db_path}: {n_customers} customers, {n_books} books, {n_orders} order line items.")
    finally:
        conn.close()


def main() -> int:
    config = load_config()
    db_path = resolve_db_path(config)
    seed(config, db_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
