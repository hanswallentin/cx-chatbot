"""SQLite access. This module is the only thing in the whole system allowed
to touch the database directly — everything else goes through the REST API.
"""
import sqlite3
from typing import Iterator

from fastapi import Depends

from app.config import database_path


def get_db_path() -> str:
    """FastAPI dependency, overridden in tests to point at a disposable DB."""
    return database_path()


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db(db_path: str = Depends(get_db_path)) -> Iterator[sqlite3.Connection]:
    """FastAPI dependency yielding a request-scoped connection.

    Depends on get_db_path so tests can override just that (cheap) piece via
    app.dependency_overrides to point every endpoint at a disposable DB.
    """
    conn = get_connection(db_path)
    try:
        yield conn
    finally:
        conn.close()
