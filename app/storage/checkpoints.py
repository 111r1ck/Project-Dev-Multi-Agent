import os
import sqlite3
from contextlib import AbstractContextManager
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver

from app.config import settings

_CHECKPOINTER: Any | None = None
_SQLITE_CONN: sqlite3.Connection | None = None
_POSTGRES_CTX: AbstractContextManager | None = None


def get_checkpointer():
    global _CHECKPOINTER, _SQLITE_CONN, _POSTGRES_CTX

    if _CHECKPOINTER is not None:
        return _CHECKPOINTER

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

        _POSTGRES_CTX = PostgresSaver.from_conn_string(
            conn_string,
            pipeline=settings.checkpointer_postgres_pipeline,
        )
        _CHECKPOINTER = _POSTGRES_CTX.__enter__()
        if settings.checkpointer_postgres_auto_setup:
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
