"""DuckDB adapter implementation."""

from __future__ import annotations

from typing import ClassVar

from sqlbuild.adapter.classes.duckdb_backed_adapter import DuckDbBackedAdapter
from sqlbuild.adapter.types import BuiltinAdapter


class DuckDbAdapter(DuckDbBackedAdapter):
    """First-class DuckDB adapter with full method coverage."""

    adapter_name: ClassVar[str] = BuiltinAdapter.DUCKDB.value
