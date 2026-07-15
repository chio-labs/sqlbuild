"""Public decorator API for SQLBuild model lifecycle hooks."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any, cast

from sqlbuild.executor.run.models import HookContext, HookSkipResult
from sqlbuild.python_nodes.models import HookDefinition

__all__ = ("HookContext", "HookDefinition", "HookSkipResult", "get_hook_definition", "hook")


def _decorate_hook(
    *,
    function: Callable[..., object],
    name: str | None = None,
    description: str | None = None,
) -> Callable[..., object]:
    hook_function: Any = cast(Any, function)
    hook_function.__sqlbuild_hook__ = HookDefinition(
        name=name or hook_function.__name__,
        description=description if description is not None else inspect.getdoc(function),
    )
    return function


def hook(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild model lifecycle hook."""

    if function is not None:
        return _decorate_hook(function=function, name=name, description=description)

    def decorate(inner: Callable[..., object]) -> Callable[..., object]:
        return _decorate_hook(function=inner, name=name, description=description)

    return decorate


def get_hook_definition(function: Callable[..., object]) -> HookDefinition | None:
    """Return SQLBuild hook metadata from a decorated function, if present."""

    value: Any = getattr(function, "__sqlbuild_hook__", None)
    if isinstance(value, HookDefinition):
        return value
    return None
