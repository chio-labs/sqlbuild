"""Migration fingerprints computed at most once per model definition and reused across runs."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from collections.abc import Mapping
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from sqlbuild.compiler.planner._helpers.changes.metadata import without_declared_columns_hash
from sqlbuild.compiler.planner._helpers.migrations.fingerprint import (
    build_migration_fingerprint,
    migration_fingerprint_ref_names,
)
from sqlbuild.compiler.planner.constants import MIGRATION_FINGERPRINT_ALGORITHM

type _FingerprintKey = tuple[str, str, str | None, tuple[tuple[str, str], ...]]

_CACHE_VERSION: int = 1
_CACHE_DIRECTORY_NAME: str = f"migration-fingerprints-v{_CACHE_VERSION}"
_CACHE_DATABASE_NAME: str = "migration-fingerprints.sqlite3"
_CACHE_ENTRY_SEPARATOR: str = "\n"
_MAX_CACHE_ENTRY_BYTES: int = 4_096
_SQLITE_TIMEOUT_SECONDS: float = 0.1
_CREATE_CACHE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS migration_fingerprint (
    cache_key TEXT PRIMARY KEY,
    payload TEXT NOT NULL
)
"""


class MigrationFingerprintCache:
    """Reuse migration fingerprints across rename maps, planning phases, and invocations."""

    def __init__(self, *, root: Path | None = None) -> None:
        self._ref_names: dict[tuple[str, str], frozenset[str]] = {}
        self._fingerprints: dict[_FingerprintKey, str | None] = {}
        self._database_path: Path | None = (
            None if root is None else root / _CACHE_DIRECTORY_NAME / _CACHE_DATABASE_NAME
        )
        self._connection: sqlite3.Connection | None = None
        self._connection_opened: bool = False
        self._pending: dict[str, str] = {}
        self._shared_digest: str = _shared_digest() if root is not None else ""

    def fingerprint(
        self,
        *,
        query_sql: str,
        metadata_json: str,
        ref_identities: Mapping[str, str],
        dialect: str | None,
    ) -> str | None:
        """Return the migration fingerprint, keyed only by the renames this model can see."""

        metadata_json = without_declared_columns_hash(metadata_json)
        definition: tuple[str, str] = (query_sql, metadata_json)
        names: frozenset[str] | None = self._ref_names.get(definition)
        if names is None:
            names = migration_fingerprint_ref_names(
                query_sql=query_sql, metadata_json=metadata_json
            )
            self._ref_names[definition] = names
        visible: dict[str, str] = {
            name: ref_identities[name] for name in sorted(names) if name in ref_identities
        }
        key: _FingerprintKey = (query_sql, metadata_json, dialect, tuple(visible.items()))
        if key in self._fingerprints:
            return self._fingerprints[key]
        cache_key: str = self._cache_key(key)
        found: bool
        stored: str | None
        found, stored = self._stored(cache_key)
        if not found:
            stored = build_migration_fingerprint(
                query_sql=query_sql,
                metadata_json=metadata_json,
                ref_identities=visible,
                dialect=dialect,
            )
            self._remember(cache_key=cache_key, fingerprint=stored)
        self._fingerprints[key] = stored
        return stored

    def persist(self) -> None:
        """Write fingerprints computed since the last persist; failures only skip reuse."""

        pending: dict[str, str] = self._pending
        self._pending = {}
        connection: sqlite3.Connection | None = self._connection
        self._connection = None
        self._connection_opened = False
        try:
            if pending and self._database_path is not None:
                if connection is None:
                    self._database_path.parent.mkdir(parents=True, exist_ok=True)
                    connection = sqlite3.connect(
                        self._database_path, timeout=_SQLITE_TIMEOUT_SECONDS
                    )
                _ = connection.execute(_CREATE_CACHE_TABLE_SQL)
                _ = connection.executemany(
                    "INSERT OR REPLACE INTO migration_fingerprint (cache_key, payload) "
                    "VALUES (?, ?)",
                    pending.items(),
                )
                connection.commit()
        except (OSError, sqlite3.DatabaseError):
            pass
        finally:
            _close(connection)

    def _cache_key(self, key: _FingerprintKey) -> str:
        if self._database_path is None:
            return ""
        return hashlib.sha256(
            json.dumps(
                [self._shared_digest, *key[:3], [list(item) for item in key[3]]],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def _stored(self, cache_key: str) -> tuple[bool, str | None]:
        connection: sqlite3.Connection | None = self._open()
        if connection is None:
            return False, None
        try:
            row: tuple[object] | None = connection.execute(
                "SELECT payload FROM migration_fingerprint WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        except sqlite3.DatabaseError:
            self._connection = None
            _close(connection)
            return False, None
        return (
            (False, None)
            if row is None
            else _fingerprint_from_contents(contents=row[0], expected_cache_key=cache_key)
        )

    def _open(self) -> sqlite3.Connection | None:
        if self._connection_opened:
            return self._connection
        self._connection_opened = True
        if self._database_path is None or not self._database_path.is_file():
            return None
        try:
            self._connection = sqlite3.connect(self._database_path, timeout=_SQLITE_TIMEOUT_SECONDS)
        except (OSError, sqlite3.DatabaseError):
            self._connection = None
        return self._connection

    def _remember(self, *, cache_key: str, fingerprint: str | None) -> None:
        if self._database_path is None:
            return
        serialized: str = json.dumps(
            {"v": _CACHE_VERSION, "k": cache_key, "f": fingerprint},
            separators=(",", ":"),
            sort_keys=True,
        )
        self._pending[cache_key] = _CACHE_ENTRY_SEPARATOR.join(
            (_entry_digest(cache_key=cache_key, serialized=serialized), serialized)
        )


def _fingerprint_from_contents(
    *, contents: object, expected_cache_key: str
) -> tuple[bool, str | None]:
    if not isinstance(contents, str) or len(contents) > _MAX_CACHE_ENTRY_BYTES:
        return False, None
    stored_digest, separator, serialized = contents.partition(_CACHE_ENTRY_SEPARATOR)
    if (
        not separator
        or not stored_digest.isascii()
        or not hmac.compare_digest(
            stored_digest, _entry_digest(cache_key=expected_cache_key, serialized=serialized)
        )
    ):
        return False, None
    try:
        payload: object = json.loads(serialized)
    except (ValueError, RecursionError):
        return False, None
    values: dict[str, Any] = cast(dict[str, Any], payload) if isinstance(payload, dict) else {}
    fingerprint: object = values.get("f")
    if (
        values.get("v") != _CACHE_VERSION
        or values.get("k") != expected_cache_key
        or not (fingerprint is None or isinstance(fingerprint, str))
    ):
        return False, None
    return True, cast(str | None, fingerprint)


def _entry_digest(*, cache_key: str, serialized: str) -> str:
    digest: Any = hashlib.sha256(cache_key.encode())
    digest.update(b"\0")
    digest.update(serialized.encode())
    return digest.hexdigest()


def _shared_digest() -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "algorithm": MIGRATION_FINGERPRINT_ALGORITHM,
                "cache_version": _CACHE_VERSION,
                "sqlbuild_version": _package_version("sqlbuild"),
                "polyglot_version": _package_version("polyglot-sql-chio"),
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()


def _package_version(package: str) -> str:
    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _close(connection: sqlite3.Connection | None) -> None:
    if connection is None:
        return
    try:
        connection.close()
    except sqlite3.DatabaseError:
        pass
