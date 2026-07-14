"""Decorator implementation for SQLBuild checks."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Sequence
from typing import Any, cast

from sqlbuild.python_nodes.models import CheckDefinition, SqlResourceRef
from sqlbuild.python_nodes.types import PythonCheckSeverity


def _decorate_check(
    *,
    function: Callable[..., object],
    depends_on: tuple[Callable[..., object] | SqlResourceRef, ...],
    name: str | None = None,
    severity: str | PythonCheckSeverity = PythonCheckSeverity.ERROR,
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
) -> Callable[..., object]:
    check_function: Any = cast(Any, function)
    definition: CheckDefinition = CheckDefinition(
        name=name or check_function.__name__,
        depends_on=depends_on,
        severity=PythonCheckSeverity(severity),
        tags=tuple(tags),
        group=group,
        description=description if description is not None else inspect.getdoc(function),
        meta=meta,
    )
    check_function.__sqlbuild_check__ = definition
    return function


def check(
    *,
    depends_on: Callable[..., object]
    | SqlResourceRef
    | tuple[Callable[..., object] | SqlResourceRef, ...]
    | list[Callable[..., object] | SqlResourceRef],
    name: str | None = None,
    severity: str | PythonCheckSeverity = PythonCheckSeverity.ERROR,
    tags: Sequence[str] = (),
    group: str | None = None,
    description: str | None = None,
    meta: dict[str, object] | None = None,
) -> Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild check."""

    normalized_deps: tuple[Callable[..., object] | SqlResourceRef, ...] = _normalize_depends_on(
        depends_on
    )

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        return _decorate_check(
            function=inner,
            name=name,
            depends_on=normalized_deps,
            severity=severity,
            tags=tags,
            group=group,
            description=description,
            meta=meta,
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


def get_check_definition(function: Callable[..., object]) -> CheckDefinition | None:
    """Return SQLBuild check metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_check__", None)
    if isinstance(value, CheckDefinition):
        return value
    return None
