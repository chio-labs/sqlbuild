"""Decorator implementation for SQLBuild tasks."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any, cast, overload

from sqlbuild.shared.models import RetryPolicy, TaskDefinition


def _decorate_task(
    function: Callable[..., object],
    *,
    name: str | None = None,
    depends_on: tuple[Callable[..., object], ...] = (),
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
    retry: RetryPolicy | None = None,
) -> Callable[..., object]:
    task_function: Any = cast(Any, function)
    definition: TaskDefinition = TaskDefinition(
        name=name or task_function.__name__,
        depends_on=depends_on,
        tags=tuple(tags),
        group=group,
        description=description if description is not None else inspect.getdoc(function),
        meta=meta,
        retry=retry,
    )
    task_function.__sqlbuild_task__ = definition
    return function


@overload
def task(function: Callable[..., object], /) -> Callable[..., object]: ...


@overload
def task(
    *,
    name: str | None = None,
    depends_on: Callable[..., object]
    | tuple[Callable[..., object], ...]
    | list[Callable[..., object]] = (),
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
    retry: RetryPolicy | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]: ...


def task(
    function: Callable[..., object] | None = None,
    /,
    *,
    name: str | None = None,
    depends_on: Callable[..., object]
    | tuple[Callable[..., object], ...]
    | list[Callable[..., object]] = (),
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
    retry: RetryPolicy | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild task."""

    normalized_deps: tuple[Callable[..., object], ...] = _normalize_depends_on(depends_on)
    if function is not None:
        return _decorate_task(
            function,
            name=name,
            depends_on=normalized_deps,
            tags=tags,
            group=group,
            description=description,
            meta=meta,
            retry=retry,
        )

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        return _decorate_task(
            inner,
            name=name,
            depends_on=normalized_deps,
            tags=tags,
            group=group,
            description=description,
            meta=meta,
            retry=retry,
        )

    return decorate


def _normalize_depends_on(
    value: Callable[..., object] | tuple[Callable[..., object], ...] | list[Callable[..., object]],
) -> tuple[Callable[..., object], ...]:
    if callable(value):
        return (value,)
    return tuple(value)


def get_task_definition(function: Callable[..., object]) -> TaskDefinition | None:
    """Return SQLBuild task metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_task__", None)
    if isinstance(value, TaskDefinition):
        return value
    return None
