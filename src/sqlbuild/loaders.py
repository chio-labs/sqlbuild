"""Public decorator API for SQLBuild source loaders."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any, cast, overload

from sqlbuild.shared.models import LoaderDefinition
from sqlbuild.shared.types import LoaderColumnSpec
from sqlbuild.spec.models.source import SourceColumnEntry
from sqlbuild.spec.models.types import SourceWriteStrategy


def _decorate_loader(
    function: Callable[..., object],
    *,
    name: str | None = None,
    depends_on: tuple[Callable[..., object], ...] = (),
    target: str | None = None,
    write_strategy: str | None = None,
    cursor_column: str | None = None,
    unique_key: str | Sequence[str] | None = None,
    columns: Sequence[LoaderColumnSpec | SourceColumnEntry] = (),
    contract: str | None = None,
) -> Callable[..., object]:
    loader_function: Any = cast(Any, function)
    definition: LoaderDefinition = LoaderDefinition(
        name=name or loader_function.__name__,
        depends_on=depends_on,
        target=target,
        write_strategy=_normalize_write_strategy(write_strategy),
        cursor_column=cursor_column,
        unique_key=_normalize_unique_key(unique_key),
        columns=_normalize_columns(columns),
        contract=contract,
    )
    loader_function.__sqlbuild_loader__ = definition
    return function


@overload
def loader(function: Callable[..., object], /) -> Callable[..., object]: ...


@overload
def loader(
    *,
    name: str | None = None,
    depends_on: tuple[Callable[..., object], ...] | list[Callable[..., object]] = (),
    target: str | None = None,
    write_strategy: str | None = None,
    cursor_column: str | None = None,
    unique_key: str | Sequence[str] | None = None,
    columns: Sequence[LoaderColumnSpec | SourceColumnEntry] = (),
    contract: str | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


def loader(
    function: Callable[..., object] | None = None,
    /,
    *,
    name: str | None = None,
    depends_on: tuple[Callable[..., object], ...] | list[Callable[..., object]] = (),
    target: str | None = None,
    write_strategy: str | None = None,
    cursor_column: str | None = None,
    unique_key: str | Sequence[str] | None = None,
    columns: Sequence[LoaderColumnSpec | SourceColumnEntry] = (),
    contract: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild source loader."""

    normalized_deps: tuple[Callable[..., object], ...] = tuple(depends_on)
    if function is not None:
        return _decorate_loader(
            function,
            name=name,
            depends_on=normalized_deps,
            target=target,
            write_strategy=write_strategy,
            cursor_column=cursor_column,
            unique_key=unique_key,
            columns=columns,
            contract=contract,
        )

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        return _decorate_loader(
            inner,
            name=name,
            depends_on=normalized_deps,
            target=target,
            write_strategy=write_strategy,
            cursor_column=cursor_column,
            unique_key=unique_key,
            columns=columns,
            contract=contract,
        )

    return decorate


def _normalize_unique_key(value: str | Sequence[str] | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    return tuple(value)


def _normalize_write_strategy(value: str | None) -> SourceWriteStrategy | None:
    if value is None:
        return None
    return SourceWriteStrategy(value)


def _normalize_columns(
    columns: Sequence[LoaderColumnSpec | SourceColumnEntry],
) -> tuple[SourceColumnEntry, ...]:
    normalized: list[SourceColumnEntry] = []
    column: LoaderColumnSpec | SourceColumnEntry
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


def get_loader_definition(function: Callable[..., object]) -> LoaderDefinition | None:
    """Return SQLBuild loader metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_loader__", None)
    if isinstance(value, LoaderDefinition):
        return value
    return None
