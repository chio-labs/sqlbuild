"""Integration tests for snapshot run execution."""

from __future__ import annotations

from typing import ClassVar

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter


class ZeroCopyDuckDbAdapter(DuckDbAdapter):
    """DuckDB test adapter that exercises the cheap-reuse executor path."""

    adapter_name: ClassVar[str] = "duckdb_zero_copy_snapshot_test"

    def supports_zero_copy_clone(self) -> bool:
        return True
