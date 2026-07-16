"""Public decorator API for SQLBuild model lifecycle hooks."""

from __future__ import annotations

from collections.abc import Callable

from sqlbuild.executor.run.models import HookContext, HookSkipResult
from sqlbuild.python_nodes.main.apply_hook import apply_hook
from sqlbuild.python_nodes.main.read_hook_definition import read_hook_definition
from sqlbuild.python_nodes.models import HookDefinition

__all__ = ("HookContext", "HookDefinition", "HookSkipResult", "get_hook_definition", "hook")


def hook(
    function: Callable[..., object] | None = None,
    *,
    name: str | None = None,
    description: str | None = None,
) -> Callable[..., object] | Callable[[Callable[..., object]], Callable[..., object]]:
    """Mark a Python function as a SQLBuild model lifecycle hook."""

    return apply_hook(function=function, name=name, description=description)


def get_hook_definition(function: Callable[..., object]) -> HookDefinition | None:
    """Return SQLBuild hook metadata from a decorated function, if present."""

    return read_hook_definition(function)
