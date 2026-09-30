"""SQLite-backed content-addressed store for deterministic per-file compile facts."""

from __future__ import annotations

import hashlib
import hmac
import pickle
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path
from types import TracebackType
from typing import Any

from sqlbuild.compiler.fact_cache._helpers.code_identity import installed_code_identity
from sqlbuild.compiler.fact_cache._helpers.restricted_pickle import (
    dump_fact_payload,
    load_fact_payload,
)
from sqlbuild.compiler.fact_cache.constants import (
    FACT_CACHE_CREATE_SLOT_INDEX_SQL,
    FACT_CACHE_CREATE_TABLE_SQL,
    FACT_CACHE_DATABASE_SUFFIX,
    FACT_CACHE_DIRECTORY_PREFIX,
    FACT_CACHE_MAX_ENTRY_BYTES,
    FACT_CACHE_QUERY_CHUNK_SIZE,
    FACT_CACHE_SQLITE_TIMEOUT_SECONDS,
    FACT_CACHE_VERSION,
)
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.profiling.main.record import record_compile_timing

_READ_ERRORS: tuple[type[BaseException], ...] = (
    OSError,
    sqlite3.DatabaseError,
    pickle.UnpicklingError,
    AttributeError,
    EOFError,
    ImportError,
    IndexError,
    KeyError,
    TypeError,
    ValueError,
    RecursionError,
    MemoryError,
)


class FactCacheStore:
    """Reuse exact facts keyed by every input and the producing code; faults are misses."""

    def __init__(self, *, root: Path | None, namespace: str, algorithm: str) -> None:
        self._database_path: Path | None = (
            None
            if root is None
            else root
            / f"{FACT_CACHE_DIRECTORY_PREFIX}{FACT_CACHE_VERSION}"
            / f"{namespace}{FACT_CACHE_DATABASE_SUFFIX}"
        )
        self._key_prefix: bytes = (
            f"{FACT_CACHE_VERSION}\0{namespace}\0{algorithm}\0".encode()
            + (installed_code_identity().encode() if root is not None else b"")
            + b"\0"
        )
        self._pending: dict[str, tuple[str, str, bytes]] = {}
        self._hits: int = 0
        self._misses: int = 0

    @property
    def enabled(self) -> bool:
        """Return whether this invocation reads and publishes cached facts."""

        return self._database_path is not None

    def __enter__(self) -> FactCacheStore:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_value, traceback
        try:
            if exc_type is None:
                self._write_pending()
        finally:
            self._pending.clear()
            if self._database_path is not None:
                record_compile_metric(metric="fact_cache_hits", value=self._hits)
                record_compile_metric(metric="fact_cache_misses", value=self._misses)

    def key(self, *parts: str | bytes) -> str:
        """Return the exact identity of one fact computed from the given ordered inputs."""

        digest: Any = hashlib.sha256(self._key_prefix)
        for part in parts:
            encoded: bytes = (
                part if isinstance(part, bytes) else part.encode("utf-8", "surrogatepass")
            )
            digest.update(len(encoded).to_bytes(8, "little"))
            digest.update(encoded)
        return str(digest.hexdigest())

    def read_many(self, keys: Sequence[str]) -> dict[str, object]:
        """Return verified cached values for the requested keys; every fault is a miss."""

        found: dict[str, object] = {}
        if self._database_path is None or not keys:
            return found
        if self._database_path.is_file():
            try:
                with closing(
                    sqlite3.connect(
                        f"file:{self._database_path}?mode=ro",
                        uri=True,
                        timeout=FACT_CACHE_SQLITE_TIMEOUT_SECONDS,
                    )
                ) as connection:
                    unique_keys: tuple[str, ...] = tuple(dict.fromkeys(keys))
                    for start in range(0, len(unique_keys), FACT_CACHE_QUERY_CHUNK_SIZE):
                        chunk: tuple[str, ...] = unique_keys[
                            start : start + FACT_CACHE_QUERY_CHUNK_SIZE
                        ]
                        placeholders: str = ",".join("?" for _ in chunk)
                        rows: list[tuple[object, object, object]] = connection.execute(
                            f"SELECT cache_key, digest, payload FROM fact "
                            f"WHERE cache_key IN ({placeholders})",
                            chunk,
                        ).fetchall()
                        for cache_key, digest, payload in rows:
                            value: object | None = _verified_value(
                                cache_key=cache_key, digest=digest, payload=payload
                            )
                            if value is not None and isinstance(cache_key, str):
                                found[cache_key] = value
            except _READ_ERRORS:
                found = {}
        self._hits += sum(1 for key in keys if key in found)
        self._misses += sum(1 for key in keys if key not in found)
        return found

    def stage(self, *, key: str, slot: str, value: object) -> None:
        """Queue one freshly computed fact for publication after a successful invocation."""

        if self._database_path is None:
            return
        try:
            payload: bytes = dump_fact_payload(value)
        except (pickle.PicklingError, TypeError, AttributeError, RecursionError, ValueError):
            return
        if len(payload) > FACT_CACHE_MAX_ENTRY_BYTES:
            return
        self._pending[key] = (slot, _entry_digest(cache_key=key, payload=payload), payload)

    def _write_pending(self) -> None:
        if self._database_path is None or not self._pending:
            return
        with record_compile_timing("cache_publication_ms"):
            try:
                self._database_path.parent.mkdir(parents=True, exist_ok=True)
                with (
                    closing(
                        sqlite3.connect(
                            self._database_path, timeout=FACT_CACHE_SQLITE_TIMEOUT_SECONDS
                        )
                    ) as connection,
                    connection,
                ):
                    _ = connection.execute(FACT_CACHE_CREATE_TABLE_SQL)
                    _ = connection.execute(FACT_CACHE_CREATE_SLOT_INDEX_SQL)
                    _ = connection.executemany(
                        "DELETE FROM fact WHERE slot = ? AND cache_key <> ?",
                        ((slot, key) for key, (slot, _digest, _payload) in self._pending.items()),
                    )
                    _ = connection.executemany(
                        "INSERT OR REPLACE INTO fact (cache_key, slot, digest, payload) "
                        "VALUES (?, ?, ?, ?)",
                        (
                            (key, slot, digest, payload)
                            for key, (slot, digest, payload) in self._pending.items()
                        ),
                    )
            except (OSError, sqlite3.DatabaseError):
                return


def _entry_digest(*, cache_key: str, payload: bytes) -> str:
    digest: Any = hashlib.sha256(cache_key.encode())
    digest.update(b"\0")
    digest.update(payload)
    return str(digest.hexdigest())


def _verified_value(*, cache_key: object, digest: object, payload: object) -> object | None:
    if (
        not isinstance(cache_key, str)
        or not isinstance(digest, str)
        or not isinstance(payload, bytes)
        or len(payload) > FACT_CACHE_MAX_ENTRY_BYTES
        or not hmac.compare_digest(digest, _entry_digest(cache_key=cache_key, payload=payload))
    ):
        return None
    try:
        return load_fact_payload(payload)
    except _READ_ERRORS:
        return None
