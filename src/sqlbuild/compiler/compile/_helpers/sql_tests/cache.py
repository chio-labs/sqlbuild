"""Versioned project-local cache for SQL test CTE extraction."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from types import TracebackType
from typing import Any, cast

from sqlbuild.compiler.compile._helpers.sql_tests.core import (
    classify_sql_test_ctes,
    extract_unclassified_sql_test_ctes,
)
from sqlbuild.compiler.compile.models import CompileSqlTestCte, CompileSqlTestCtes
from sqlbuild.compiler.compile.types import SqlTestMode
from sqlbuild.compiler.profiling.main.record import record_compile_timing

_CACHE_VERSION: int = 1
_CACHE_DATABASE_NAME: str = "sql-test-ctes.sqlite3"
_MAX_CACHE_ENTRY_BYTES: int = 10_000_000
_SQLITE_TIMEOUT_SECONDS: float = 0.1
_CACHE_CTE_ROW_FIELD_COUNT: int = 2
_CREATE_CACHE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS sql_test_cte (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
)
"""


class _SqlTestCteCache:
    """Reuse exact CTE boundaries while retaining classification and validation."""

    def __init__(self, *, root: Path | None) -> None:
        self._root: Path | None = root
        self._database_path: Path | None = None
        self._connection: sqlite3.Connection | None = None
        self._pending_by_key: dict[str, str] = {}

    def __enter__(self) -> _SqlTestCteCache:
        if self._root is None:
            return self
        self._database_path = self._root / f"sql-test-ctes-v{_CACHE_VERSION}" / _CACHE_DATABASE_NAME
        if not self._database_path.is_file():
            return self
        try:
            self._connection = sqlite3.connect(
                self._database_path,
                timeout=_SQLITE_TIMEOUT_SECONDS,
            )
        except (OSError, sqlite3.DatabaseError):
            self._disable()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_value, traceback
        connection: sqlite3.Connection | None = self._connection
        self._connection = None
        try:
            if exc_type is None:
                with record_compile_timing("cache_publication_ms"):
                    connection = self._write_pending(connection=connection)
            elif connection is not None:
                connection.rollback()
        except (OSError, sqlite3.DatabaseError):
            pass
        finally:
            self._pending_by_key.clear()
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.DatabaseError:
                    pass

    def extract(self, *, sql: str, file_label: str, mode: SqlTestMode) -> CompileSqlTestCtes:
        """Return cached raw CTEs or scan and record this exact expanded SQL."""

        cache_key: str = hashlib.sha256(sql.encode()).hexdigest()
        ctes: tuple[CompileSqlTestCte, ...] | None = self._pending_ctes(cache_key=cache_key)
        if ctes is None:
            ctes = self._read_ctes(cache_key=cache_key)
        if ctes is None:
            ctes = extract_unclassified_sql_test_ctes(sql=sql, file_label=file_label)
            if self._database_path is not None:
                contents: str = _cache_contents(cache_key=cache_key, ctes=ctes)
                if len(contents.encode()) <= _MAX_CACHE_ENTRY_BYTES:
                    self._pending_by_key[cache_key] = contents
        return classify_sql_test_ctes(ctes=ctes, file_label=file_label, mode=mode)

    def _pending_ctes(self, *, cache_key: str) -> tuple[CompileSqlTestCte, ...] | None:
        contents: str | None = self._pending_by_key.get(cache_key)
        return (
            None
            if contents is None
            else _ctes_from_contents(contents=contents, cache_key=cache_key)
        )

    def _read_ctes(self, *, cache_key: str) -> tuple[CompileSqlTestCte, ...] | None:
        connection: sqlite3.Connection | None = self._connection
        if connection is None:
            return None
        try:
            row: tuple[str] | None = connection.execute(
                "SELECT payload FROM sql_test_cte WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
        except sqlite3.DatabaseError:
            self._disable()
            return None
        return None if row is None else _ctes_from_contents(contents=row[0], cache_key=cache_key)

    def _write_pending(self, *, connection: sqlite3.Connection | None) -> sqlite3.Connection | None:
        if not self._pending_by_key or self._database_path is None:
            return connection
        if connection is None:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(self._database_path, timeout=_SQLITE_TIMEOUT_SECONDS)
        _ = connection.execute(_CREATE_CACHE_TABLE_SQL)
        _ = connection.executemany(
            "INSERT OR REPLACE INTO sql_test_cte (cache_key, payload) VALUES (?, ?)",
            self._pending_by_key.items(),
        )
        connection.commit()
        return connection

    def _disable(self) -> None:
        connection: sqlite3.Connection | None = self._connection
        self._connection = None
        if connection is not None:
            try:
                connection.close()
            except sqlite3.DatabaseError:
                pass


def _cache_contents(*, cache_key: str, ctes: tuple[CompileSqlTestCte, ...]) -> str:
    serialized: str = json.dumps(
        {
            "v": _CACHE_VERSION,
            "k": cache_key,
            "c": [[cte.name, cte.sql_body] for cte in ctes],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{_cache_digest(cache_key=cache_key, serialized=serialized)}\n{serialized}"


def _ctes_from_contents(
    *, contents: object, cache_key: str
) -> tuple[CompileSqlTestCte, ...] | None:
    if not isinstance(contents, str) or len(contents.encode()) > _MAX_CACHE_ENTRY_BYTES:
        return None
    try:
        digest, separator, serialized = contents.partition("\n")
        if not separator or not hmac.compare_digest(
            digest,
            _cache_digest(cache_key=cache_key, serialized=serialized),
        ):
            return None
        payload: object = json.loads(serialized)
        if not isinstance(payload, dict) or payload.get("v") != _CACHE_VERSION:
            return None
        if payload.get("k") != cache_key or not isinstance(payload.get("c"), list):
            return None
        rows: list[object] = cast(list[object], payload["c"])
        if not all(
            isinstance(row, list)
            and len(row) == _CACHE_CTE_ROW_FIELD_COUNT
            and isinstance(row[0], str)
            and isinstance(row[1], str)
            for row in rows
        ):
            return None
        return tuple(
            CompileSqlTestCte(name=cast(list[str], row)[0], sql_body=cast(list[str], row)[1])
            for row in rows
        )
    except (ValueError, TypeError, KeyError, RecursionError, json.JSONDecodeError):
        return None


def _cache_digest(*, cache_key: str, serialized: str) -> str:
    digest: Any = hashlib.sha256(cache_key.encode())
    digest.update(b"\0")
    digest.update(serialized.encode())
    return digest.hexdigest()


@contextmanager
def cached_sql_test_cte_extractor(
    *, root: Path | None
) -> Iterator[Callable[[str, str, SqlTestMode], CompileSqlTestCtes]]:
    """Yield an exact cached SQL test CTE extractor for one compile invocation."""

    with _SqlTestCteCache(root=root) as cache:
        yield lambda sql, file_label, mode: cache.extract(
            sql=sql,
            file_label=file_label,
            mode=mode,
        )
