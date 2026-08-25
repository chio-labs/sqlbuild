"""Versioned project-local cache for SQL reference extraction."""

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

from sqlbuild.compiler.compile._helpers.refs.references import extract_sql_references
from sqlbuild.compiler.compile.exceptions import AnalysisCacheEntryError
from sqlbuild.compiler.compile.models import CompileSqlReference
from sqlbuild.compiler.references.types import SqlReferenceKind

_REFERENCE_CACHE_VERSION: int = 2
_CACHE_DATABASE_NAME: str = "sql-references.sqlite3"
_CACHE_ENTRY_SEPARATOR: str = "\n"
_MAX_CACHE_ENTRY_BYTES: int = 1_000_000
_SQLITE_TIMEOUT_SECONDS: float = 0.1
_CREATE_CACHE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS sql_reference (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
)
"""


class _SqlReferenceCache:
    """Reuse exact SQL reference facts while preserving safe scanner fallback."""

    def __init__(self, *, root: Path | None) -> None:
        self._root: Path | None = root
        self._database_path: Path | None = None
        self._connection: sqlite3.Connection | None = None
        self._pending_contents_by_key: dict[str, str] = {}

    def __enter__(self) -> _SqlReferenceCache:
        if self._root is None:
            return self
        self._database_path = (
            self._root / f"references-v{_REFERENCE_CACHE_VERSION}" / _CACHE_DATABASE_NAME
        )
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
                connection = self._write_pending(connection=connection)
            elif connection is not None:
                connection.rollback()
        except (OSError, sqlite3.DatabaseError):
            pass
        finally:
            self._pending_contents_by_key.clear()
            if connection is not None:
                try:
                    connection.close()
                except sqlite3.DatabaseError:
                    pass

    def references(self, sql: str) -> tuple[CompileSqlReference, ...]:
        """Return cached references or scan and record this exact expanded SQL."""

        cache_key: str = _reference_cache_key(sql)
        pending_contents: str | None = self._pending_contents_by_key.get(cache_key)
        if pending_contents is not None:
            pending_references: tuple[CompileSqlReference, ...] | None = _references_from_contents(
                contents=pending_contents,
                expected_cache_key=cache_key,
            )
            if pending_references is not None:
                return pending_references
        connection: sqlite3.Connection | None = self._connection
        if connection is not None:
            try:
                row: tuple[str] | None = connection.execute(
                    "SELECT payload FROM sql_reference WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
                if row is not None:
                    cached_references: tuple[CompileSqlReference, ...] | None = (
                        _references_from_contents(contents=row[0], expected_cache_key=cache_key)
                    )
                    if cached_references is not None:
                        return cached_references
            except sqlite3.DatabaseError:
                self._disable()
                connection = None

        references: tuple[CompileSqlReference, ...] = extract_sql_references(sql)
        if self._database_path is not None:
            try:
                self._pending_contents_by_key[cache_key] = _reference_contents(
                    cache_key=cache_key,
                    references=references,
                )
            except (TypeError, ValueError):
                pass
        return references

    def _write_pending(self, *, connection: sqlite3.Connection | None) -> sqlite3.Connection | None:
        if not self._pending_contents_by_key or self._database_path is None:
            return connection
        if connection is None:
            self._database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(
                self._database_path,
                timeout=_SQLITE_TIMEOUT_SECONDS,
            )
        _ = connection.execute(_CREATE_CACHE_TABLE_SQL)
        _ = connection.executemany(
            "INSERT OR REPLACE INTO sql_reference (cache_key, payload) VALUES (?, ?)",
            self._pending_contents_by_key.items(),
        )
        connection.commit()
        return connection

    def _disable(self) -> None:
        connection: sqlite3.Connection | None = self._connection
        self._connection = None
        if connection is None:
            return
        try:
            connection.close()
        except sqlite3.DatabaseError:
            pass


def _reference_cache_key(sql: str) -> str:
    return hashlib.sha256(sql.encode()).hexdigest()


def _reference_contents(*, cache_key: str, references: tuple[CompileSqlReference, ...]) -> str:
    serialized_payload: str = json.dumps(
        {
            "v": _REFERENCE_CACHE_VERSION,
            "k": cache_key,
            "r": [
                [
                    str(reference.ref_kind),
                    reference.ref_name,
                    reference.ref_package,
                    reference.call_argument_count,
                ]
                for reference in references
            ],
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return _CACHE_ENTRY_SEPARATOR.join(
        (
            _cache_entry_digest(cache_key=cache_key, serialized_payload=serialized_payload),
            serialized_payload,
        )
    )


def _references_from_contents(
    *, contents: str, expected_cache_key: str
) -> tuple[CompileSqlReference, ...] | None:
    encoded_contents: bytes = contents.encode()
    if len(encoded_contents) > _MAX_CACHE_ENTRY_BYTES:
        return None
    try:
        stored_digest, separator, serialized_payload = contents.partition(_CACHE_ENTRY_SEPARATOR)
        if not separator or not hmac.compare_digest(
            stored_digest,
            _cache_entry_digest(
                cache_key=expected_cache_key,
                serialized_payload=serialized_payload,
            ),
        ):
            return None
        payload: object = json.loads(serialized_payload)
        if not isinstance(payload, dict):
            raise AnalysisCacheEntryError("reference cache entry must be an object")
        values: dict[str, Any] = cast(dict[str, Any], payload)
        if values["v"] != _REFERENCE_CACHE_VERSION:
            raise AnalysisCacheEntryError("reference cache version mismatch")
        if values["k"] != expected_cache_key:
            raise AnalysisCacheEntryError("reference cache key mismatch")
        references_payload: object = values["r"]
        if not isinstance(references_payload, list) or not all(
            isinstance(reference, list) for reference in references_payload
        ):
            raise AnalysisCacheEntryError("reference cache facts must be arrays")
        return tuple(
            _reference_from_payload(cast(list[object], reference))
            for reference in references_payload
        )
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None


def _reference_from_payload(payload: list[object]) -> CompileSqlReference:
    reference_value_count: int = 4
    if len(payload) != reference_value_count:
        raise AnalysisCacheEntryError("reference cache fact must contain four values")
    kind, name, package, call_argument_count = payload
    if not isinstance(kind, str) or not isinstance(name, str):
        raise AnalysisCacheEntryError("reference cache kind and name must be strings")
    if package is not None and not isinstance(package, str):
        raise AnalysisCacheEntryError("reference cache package must be a string or null")
    if call_argument_count is not None and type(call_argument_count) is not int:
        raise AnalysisCacheEntryError("reference cache argument count must be an integer or null")
    return CompileSqlReference(
        ref_kind=SqlReferenceKind(kind),
        ref_name=name,
        ref_package=package,
        call_argument_count=call_argument_count,
    )


def _cache_entry_digest(*, cache_key: str, serialized_payload: str) -> str:
    digest: Any = hashlib.sha256(cache_key.encode())
    digest.update(b"\0")
    digest.update(serialized_payload.encode())
    return digest.hexdigest()


@contextmanager
def cached_sql_reference_extractor(
    *, root: Path | None
) -> Iterator[Callable[[str], tuple[CompileSqlReference, ...]]]:
    """Yield an exact cached reference extractor for one compile invocation."""

    with _SqlReferenceCache(root=root) as cache:
        yield cache.references
