import os
import sqlite3
import threading
from contextlib import AbstractContextManager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.config import settings

_CHECKPOINTER: Any | None = None
_SQLITE_CONN: sqlite3.Connection | None = None
_POSTGRES_CTX: AbstractContextManager | None = None
_CHECKPOINTER_LOCK = threading.RLock()


def _close_cached_resources() -> None:
    global _CHECKPOINTER, _SQLITE_CONN, _POSTGRES_CTX

    if _POSTGRES_CTX is not None:
        try:
            _POSTGRES_CTX.__exit__(None, None, None)
        except Exception:
            pass
    _POSTGRES_CTX = None

    if _SQLITE_CONN is not None:
        try:
            _SQLITE_CONN.close()
        except Exception:
            pass
    _SQLITE_CONN = None

    _CHECKPOINTER = None


def is_checkpointer_healthy(checkpointer: Any) -> bool:
    if checkpointer is None:
        return False

    conn = getattr(checkpointer, "conn", None)
    if conn is not None:
        # psycopg3 uses bool for .closed, psycopg2 uses int(0/1)
        if bool(getattr(conn, "closed", False)):
            return False
        if bool(getattr(conn, "broken", False)):
            return False

    return True


def get_checkpointer():
    global _CHECKPOINTER, _SQLITE_CONN, _POSTGRES_CTX

    with _CHECKPOINTER_LOCK:
        if _CHECKPOINTER is not None:
            if is_checkpointer_healthy(_CHECKPOINTER):
                return _CHECKPOINTER
            _close_cached_resources()

        backend = settings.checkpointer_backend.lower().strip()
        if backend == "postgres":
            try:
                from langgraph.checkpoint.postgres import PostgresSaver
            except ImportError:
                _CHECKPOINTER = InMemorySaver()
                return _CHECKPOINTER

            conn_string = settings.checkpointer_postgres_dsn.strip()
            if not conn_string:
                raise ValueError(
                    "CHECKPOINTER_BACKEND=postgres requires CHECKPOINTER_POSTGRES_DSN"
                )

            def _open_postgres_saver():
                ctx = PostgresSaver.from_conn_string(
                    conn_string,
                    pipeline=settings.checkpointer_postgres_pipeline,
                )
                saver = ctx.__enter__()
                return saver, ctx

            _CHECKPOINTER, _POSTGRES_CTX = _open_postgres_saver()
            if settings.checkpointer_postgres_auto_setup:
                try:
                    _CHECKPOINTER.setup()
                except Exception as exc:
                    # Rare startup race/driver edge case: reopen once on closed connection.
                    if "connection is closed" not in str(exc).lower():
                        raise
                    _close_cached_resources()
                    _CHECKPOINTER, _POSTGRES_CTX = _open_postgres_saver()
                    _CHECKPOINTER.setup()
            return _CHECKPOINTER

        if backend == "sqlite":
            try:
                from langgraph.checkpoint.sqlite import SqliteSaver
            except ImportError:
                _CHECKPOINTER = InMemorySaver()
                return _CHECKPOINTER

            sqlite_path = settings.checkpointer_sqlite_path
            sqlite_dir = os.path.dirname(sqlite_path)
            if sqlite_dir:
                os.makedirs(sqlite_dir, exist_ok=True)

            _SQLITE_CONN = sqlite3.connect(sqlite_path, check_same_thread=False)
            _CHECKPOINTER = SqliteSaver(_SQLITE_CONN)
            return _CHECKPOINTER

        _CHECKPOINTER = InMemorySaver()
        return _CHECKPOINTER


def purge_thread_checkpoints(thread_id: str) -> dict[str, Any]:
    """Delete all persisted checkpoints for a given thread/project id."""
    backend = settings.checkpointer_backend.lower().strip()
    tables = (
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_migrations",
    )

    with _CHECKPOINTER_LOCK:
        if backend == "memory":
            return {
                "backend": backend,
                "thread_id": thread_id,
                "deleted_rows": 0,
                "deleted_tables": [],
                "message": "memory backend has no persisted checkpoints to delete",
            }

        saver = get_checkpointer()
        conn = getattr(saver, "conn", None)
        deleted_rows = 0
        deleted_tables: list[str] = []

        if backend == "sqlite":
            if conn is None:
                raise RuntimeError("sqlite checkpointer connection is unavailable")
            cur = conn.cursor()
            try:
                for table in tables:
                    try:
                        cur.execute(f"DELETE FROM {table} WHERE thread_id = ?", (thread_id,))
                        if cur.rowcount and cur.rowcount > 0:
                            deleted_rows += int(cur.rowcount)
                            deleted_tables.append(table)
                    except sqlite3.OperationalError:
                        # Table may not exist in current schema/version.
                        continue
                conn.commit()
            finally:
                cur.close()
            return {
                "backend": backend,
                "thread_id": thread_id,
                "deleted_rows": deleted_rows,
                "deleted_tables": deleted_tables,
            }

        if backend == "postgres":
            if conn is None:
                raise RuntimeError("postgres checkpointer connection is unavailable")

            def _first_value(row: Any) -> Any:
                if row is None:
                    return None
                if isinstance(row, dict):
                    for _k, v in row.items():
                        return v
                    return None
                try:
                    return row[0]
                except Exception:
                    return row

            with conn.cursor() as cur:
                existing_tables: set[str] = set()
                thread_scoped_tables: set[str] = set()
                for table in tables:
                    cur.execute("SELECT to_regclass(%s)", (table,))
                    row = cur.fetchone()
                    if _first_value(row):
                        existing_tables.add(table)
                for table in existing_tables:
                    cur.execute(
                        """
                        SELECT 1
                        FROM information_schema.columns
                        WHERE table_name = %s
                          AND column_name = 'thread_id'
                        LIMIT 1
                        """,
                        (table,),
                    )
                    if cur.fetchone():
                        thread_scoped_tables.add(table)
                for table in tables:
                    if table not in thread_scoped_tables:
                        continue
                    cur.execute(
                        f'DELETE FROM "{table}" WHERE thread_id = %s',
                        (thread_id,),
                    )
                    if cur.rowcount and cur.rowcount > 0:
                        deleted_rows += int(cur.rowcount)
                        deleted_tables.append(table)
            conn.commit()
            return {
                "backend": backend,
                "thread_id": thread_id,
                "deleted_rows": deleted_rows,
                "deleted_tables": deleted_tables,
            }

        return {
            "backend": backend,
            "thread_id": thread_id,
            "deleted_rows": 0,
            "deleted_tables": [],
            "message": "unsupported backend for purge",
        }
