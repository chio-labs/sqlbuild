"""Resolve compiled resource type for SQL functions."""

from __future__ import annotations

from sqlbuild.compiler.compile.types import CompiledResourceType


def _function_resource_type(*, return_columns: tuple[object, ...]) -> CompiledResourceType:
    """Return the compiled resource type for a SQL function shape."""

    return CompiledResourceType.TABLE_FN if return_columns else CompiledResourceType.UDF


def function_node_type(*, return_columns: tuple[object, ...]) -> str:
    """Return the public node type for a SQL function shape."""

    return _function_resource_type(return_columns=return_columns).value
