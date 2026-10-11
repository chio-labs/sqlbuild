"""The compile's native SQL-test scan store, opened on first use and saved once."""

from __future__ import annotations

import logging
from pathlib import Path

import sqlbuild._native as _native
from sqlbuild.compiler.frontier.main.compiled_code_identity import compiled_code_identity
from sqlbuild.compiler.profiling.main._metric import record_compile_metric


class SqlTestScanCache:
    """The compile cache folder's scan store, keyed by the installed and native code."""

    def __init__(self, *, cache_dir: Path | None) -> None:
        self._cache_dir: Path | None = cache_dir
        self._store: _native.SqlTestScanStore | None = None

    def opened(self) -> _native.SqlTestScanStore | None:
        """The native store this compile reads and writes, or None when it has none."""

        if self._cache_dir is None or self._store is not None:
            return self._store
        error: str | None
        self._store, error = _native.SqlTestScanStore.open_in(
            str(self._cache_dir), compiled_code_identity()
        )
        if error is not None:
            logging.getLogger(__name__).debug("SQL test scan store not loaded: %s", error)
            self._cache_dir = None
        return self._store

    def save(self) -> None:
        """Persist results stored by this compile and report hit and miss counts."""

        hits, misses = (0, 0) if self._store is None else self._store.counts()
        record_compile_metric(metric="sql_test_scan_cache_hits", value=hits)
        record_compile_metric(metric="sql_test_scan_cache_misses", value=misses)
        if self._store is None:
            return
        _written, error = self._store.save()
        if error is not None:
            logging.getLogger(__name__).debug("SQL test scan store not saved: %s", error)
