"""Hook execution for model materialization lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter


def execute_hooks(
    *,
    connection: Any,
    adapter: BaseAdapter,
    hooks: object,
    phase_label: str,
) -> None:
    """Execute pre/post hook SQL strings."""

    if hooks is None:
        return
    if isinstance(hooks, str):
        adapter.execute(connection, hooks)
        return
    if isinstance(hooks, list | tuple):
        hook: object
        for hook in hooks:
            if isinstance(hook, str):
                adapter.execute(connection, hook)
            else:
                raise ValueError(f"{phase_label} hook entry must be a string, got {type(hook)}")
        return
    raise ValueError(f"{phase_label} must be a string or list of strings, got {type(hooks)}")


def render_hooks(*, hooks: object, phase_label: str) -> tuple[str, ...]:
    if hooks is None:
        return ()
    if isinstance(hooks, str):
        return (hooks,)
    if isinstance(hooks, list | tuple):
        statements: list[str] = []
        hook: object
        for hook in hooks:
            if isinstance(hook, str):
                statements.append(hook)
            else:
                raise ValueError(f"{phase_label} hook entry must be a string, got {type(hook)}")
        return tuple(statements)
    raise ValueError(f"{phase_label} must be a string or list of strings, got {type(hooks)}")
