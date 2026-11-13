"""
Storage for user-generated data (library, community).

Uses PostgreSQL when SNP_USER_DB_URL is set (needed on free hosting, whose disk
is wiped on restart) and the local SQLite database otherwise. Queries are written
once with "?" placeholders; the Postgres adapter translates them.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Iterator, Optional, Sequence

from core.paths import DATABASE_PATH
from core.settings import get_setting

USER_DB_URL_KEY = "SNP_USER_DB_URL"


def database_url() -> Optional[str]:
    url = (get_setting(USER_DB_URL_KEY) or "").strip()
    return url if url.startswith(("postgres://", "postgresql://")) else None


def backend() -> str:
    return "postgres" if database_url() else "sqlite"


class Connection:
    """Small wrapper giving SQLite and Postgres the same interface."""

    def __init__(self, raw: Any, dialect: str):
        self.raw = raw
        self.dialect = dialect

    def _sql(self, sql: str) -> str:
        return sql.replace("?", "%s") if self.dialect == "postgres" else sql

    def execute(self, sql: str, params: Sequence = ()) -> None:
        self.raw.execute(self._sql(sql), tuple(params))

    def fetch_all(self, sql: str, params: Sequence = ()) -> list[dict]:
        cursor = self.raw.execute(self._sql(sql), tuple(params))
        columns = [c[0] for c in cursor.description or []]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def fetch_one(self, sql: str, params: Sequence = ()) -> Optional[dict]:
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def insert(self, sql: str, params: Sequence = (), id_column: str = "id") -> int:
        """Run an INSERT and return the new row id."""
        if self.dialect == "postgres":
            cursor = self.raw.execute(self._sql(sql) + f" RETURNING {id_column}", tuple(params))
            return int(cursor.fetchone()[0])
        cursor = self.raw.execute(sql, tuple(params))
        return int(cursor.lastrowid)


@contextmanager
def connect() -> Iterator[Connection]:
    """Open a connection, commit on success and roll back on error."""
    url = database_url()
    if url:
        import psycopg

        raw = psycopg.connect(url, connect_timeout=10)
        conn = Connection(raw, "postgres")
    else:
        DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
        raw = sqlite3.connect(DATABASE_PATH, timeout=10)
        raw.execute("PRAGMA foreign_keys = ON")
        conn = Connection(raw, "sqlite")
    try:
        yield conn
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def id_column_sql(dialect: str) -> str:
    return "BIGSERIAL PRIMARY KEY" if dialect == "postgres" else "INTEGER PRIMARY KEY AUTOINCREMENT"
