"""Public decorator API for SQLBuild assets."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

from sqlbuild.compiler.python_nodes.types import SkipMode
from sqlbuild.executor.python_nodes.models import AssetContext
from sqlbuild.python_nodes.models import (
    AssetDefinition,
    ColumnLineageRef,
    RetryPolicy,
    SqlResourceRef,
)
from sqlbuild.python_nodes.types import ColumnLineageRefSpec, PythonNodeColumnSpec
from sqlbuild.spec.contracts.models import SourceColumnEntry

__all__ = ("AssetContext", "SkipMode", "asset", "get_asset_definition")


def _decorate_asset(
    *,
    function: Callable[..., object],
    name: str | None = None,
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...] = (),
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
    columns: Sequence[PythonNodeColumnSpec | SourceColumnEntry] = (),
    column_lineage: Mapping[str, Sequence[ColumnLineageRefSpec | ColumnLineageRef]] | None = None,
    retry: RetryPolicy | None = None,
) -> Callable[..., object]:
    asset_function: Any = cast(Any, function)
    definition: AssetDefinition = AssetDefinition(
        name=name or asset_function.__name__,
        depends_on=depends_on,
        tags=tuple(tags),
        group=group,
        description=description if description is not None else inspect.getdoc(function),
        meta=meta,
        columns=_normalize_columns(columns),
        column_lineage=_normalize_column_lineage(column_lineage),
        retry=retry,
    )
    asset_function.__sqlbuild_asset__ = definition
    return function


def asset(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    depends_on: Callable[..., object]
    | SqlResourceRef
    | tuple[Callable[..., object] | SqlResourceRef, ...]
    | list[Callable[..., object] | SqlResourceRef] = (),
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
    columns: Sequence[PythonNodeColumnSpec | SourceColumnEntry] = (),
    column_lineage: Mapping[str, Sequence[ColumnLineageRefSpec | ColumnLineageRef]] | None = None,
    retry: RetryPolicy | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild asset."""

    normalized_deps: tuple[Callable[..., object] | SqlResourceRef, ...] = _normalize_depends_on(
        depends_on
    )
    if function is not None:
        return _decorate_asset(
            function=function,
            name=name,
            depends_on=normalized_deps,
            tags=tags,
            group=group,
            description=description,
            meta=meta,
            columns=columns,
            column_lineage=column_lineage,
            retry=retry,
        )

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        return _decorate_asset(
            function=inner,
            name=name,
            depends_on=normalized_deps,
            tags=tags,
            group=group,
            description=description,
            meta=meta,
            columns=columns,
            column_lineage=column_lineage,
            retry=retry,
        )

    return decorate


def _normalize_depends_on(
    value: Callable[..., object]
    | SqlResourceRef
    | tuple[Callable[..., object] | SqlResourceRef, ...]
    | list[Callable[..., object] | SqlResourceRef],
) -> tuple[Callable[..., object] | SqlResourceRef, ...]:
    if callable(value) or isinstance(value, SqlResourceRef):
        return (value,)
    return tuple(value)


def _normalize_columns(
    columns: Sequence[PythonNodeColumnSpec | SourceColumnEntry],
) -> tuple[SourceColumnEntry, ...]:
    normalized: list[SourceColumnEntry] = []
    column: PythonNodeColumnSpec | SourceColumnEntry
    for column in columns:
        if isinstance(column, SourceColumnEntry):
            normalized.append(column)
            continue
        column_type: object = column.get("type")
        nullable: object = column.get("nullable")
        description: object = column.get("description")
        meta: object = column.get("meta", {})
        normalized.append(
            SourceColumnEntry(
                name=str(column["name"]),
                type=str(column_type) if column_type is not None else None,
                nullable=bool(nullable) if nullable is not None else None,
                description=str(description) if description is not None else None,
                meta=meta if isinstance(meta, dict) else {},
            )
        )
    return tuple(normalized)


def _normalize_column_lineage(
    value: Mapping[str, Sequence[ColumnLineageRefSpec | ColumnLineageRef]] | None,
) -> dict[str, tuple[ColumnLineageRef, ...]] | None:
    if value is None:
        return None
    normalized: dict[str, tuple[ColumnLineageRef, ...]] = {}
    for column_name, refs in value.items():
        normalized_refs: list[ColumnLineageRef] = []
        for ref in refs:
            normalized_refs.append(_normalize_column_lineage_ref(ref))
        normalized[str(column_name)] = tuple(normalized_refs)
    return normalized


def _normalize_column_lineage_ref(
    value: ColumnLineageRefSpec | ColumnLineageRef,
) -> ColumnLineageRef:
    if isinstance(value, ColumnLineageRef):
        return value
    return ColumnLineageRef(node=str(value["node"]), column=str(value["column"]))


def get_asset_definition(function: Callable[..., object]) -> AssetDefinition | None:
    """Return SQLBuild asset metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_asset__", None)
    if isinstance(value, AssetDefinition):
        return value
    return None
