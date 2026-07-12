"""DuckDB adapter implementation."""

from __future__ import annotations

from typing import ClassVar

from sqlbuild.adapter.types import BuiltinAdapter
from sqlbuild.adapters.shared.classes.duckdb import DuckDbBackedAdapter


class DuckDbAdapter(DuckDbBackedAdapter):
    """First-class DuckDB adapter with full method coverage."""

    adapter_name: ClassVar[str] = BuiltinAdapter.DUCKDB.value
