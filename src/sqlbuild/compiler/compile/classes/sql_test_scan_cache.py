"""Per-file SQL-test scan results reused across compiles from the shared native store."""

from __future__ import annotations

import logging
from collections.abc import Callable, Sequence
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.compile.constants import (
    SQL_TEST_SCAN_STORE_FILE_NAME,
    SQL_TEST_SCAN_STORE_VERSION,
)
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.compiler.profiling.main._metric import record_compile_metric
from sqlbuild.compiler.sql_analysis.models import SqlLexicalSyntax


class SqlTestScanCache:
    """Whole per-file scan results keyed by installed code, scan algorithm, rules and text."""

    def __init__(self, *, cache_dir: Path | None) -> None:
        self._path: Path | None = (
            None if cache_dir is None else cache_dir / SQL_TEST_SCAN_STORE_FILE_NAME
        )
        self._store: _native.SqlTestScanStore | None = None
        self._hits: int = 0
        self._misses: int = 0

    def read[T](
        self,
        *,
        algorithm: str,
        syntax: SqlLexicalSyntax,
        parts: Sequence[str],
        decode: Callable[[bytes], T | None],
    ) -> T | None:
        """Return one file's decoded stored result, or None when it must be scanned again."""

        store: _native.SqlTestScanStore | None = self._opened()
        if store is None:
            return None
        found: bytes | None = store.get([algorithm, syntax.cache_key, *parts])
        decoded: T | None = None if found is None else decode(found)
        if decoded is None:
            self._misses += 1
        else:
            self._hits += 1
        return decoded

    def write(
        self, *, algorithm: str, syntax: SqlLexicalSyntax, parts: Sequence[str], value: bytes
    ) -> None:
        """Store one file's complete scan result; callers never store failed scans."""

        store: _native.SqlTestScanStore | None = self._opened()
        if store is not None:
            store.put([algorithm, syntax.cache_key, *parts], value)

    def save(self) -> None:
        """Persist results stored by this compile and report hit and miss counts."""

        record_compile_metric(metric="sql_test_scan_cache_hits", value=self._hits)
        record_compile_metric(metric="sql_test_scan_cache_misses", value=self._misses)
        if self._store is None or self._path is None:
            return
        try:
            _ = self._store.save(str(self._path))
        except (OSError, RuntimeError) as error:
            logging.getLogger(__name__).debug("SQL test scan store not saved: %s", error)

    def _opened(self) -> _native.SqlTestScanStore | None:
        if self._path is None:
            return None
        if self._store is None:
            environment: str = _native.content_digest(
                [SQL_TEST_SCAN_STORE_VERSION, compiled_code_identity()]
            )
            try:
                self._store = _native.SqlTestScanStore(str(self._path), environment)
            except (OSError, RuntimeError) as error:
                logging.getLogger(__name__).debug("SQL test scan store not loaded: %s", error)
                self._path = None
                return None
        return self._store
