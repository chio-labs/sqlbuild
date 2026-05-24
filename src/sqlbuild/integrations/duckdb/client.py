"""DuckDB adapter implementation."""

from __future__ import annotations

from typing import ClassVar

from sqlbuild.adapter.shared.types import BuiltinAdapter
from sqlbuild.integrations.shared.classes.duckdb import DuckDbBackedAdapter


class DuckDbAdapter(DuckDbBackedAdapter):
    """First-class DuckDB adapter with full method coverage."""

    adapter_name: ClassVar[str] = BuiltinAdapter.DUCKDB.value
