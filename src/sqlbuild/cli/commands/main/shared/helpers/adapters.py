"""Adapter resolution from project configuration."""

from __future__ import annotations

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.types import BuiltinAdapter


def resolve_adapter(adapter_name: str) -> BaseAdapter:
    """Resolve an adapter name from project config to a built-in adapter instance."""

    match adapter_name:
        case BuiltinAdapter.DUCKDB:
            from sqlbuild.integrations.duckdb.client import DuckDbAdapter

            return DuckDbAdapter()
        case _:
            available: str = ", ".join(a.value for a in BuiltinAdapter)
            raise ValueError(
                f"Unknown adapter '{adapter_name}'. Available built-in adapters: {available}"
            )
