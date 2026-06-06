"""Hook execution for model materialization lifecycle."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry


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
    if isinstance(hooks, SqlHookEntry):
        adapter.execute(connection, hooks.statement)
        return
    if isinstance(hooks, PythonHookEntry):
        raise ExecutorInputError("python hooks are not executable in this release slice")
    if isinstance(hooks, list | tuple):
        hook: object
        for hook in hooks:
            if isinstance(hook, str):
                adapter.execute(connection, hook)
            elif isinstance(hook, SqlHookEntry):
                adapter.execute(connection, hook.statement)
            elif isinstance(hook, PythonHookEntry):
                raise ExecutorInputError("python hooks are not executable in this release slice")
            else:
                raise ExecutorInputError(
                    f"{phase_label} hook entry must be a string or typed hook, got {type(hook)}"
                )
        return
    raise ExecutorInputError(
        f"{phase_label} must be a string, typed hook, or list of hooks, got {type(hooks)}"
    )


def render_hooks(*, hooks: object, phase_label: str) -> tuple[str, ...]:
    if hooks is None:
        return ()
    if isinstance(hooks, str):
        return (hooks,)
    if isinstance(hooks, SqlHookEntry):
        return (hooks.statement,)
    if isinstance(hooks, PythonHookEntry):
        return ()
    if isinstance(hooks, list | tuple):
        statements: list[str] = []
        hook: object
        for hook in hooks:
            if isinstance(hook, str):
                statements.append(hook)
            elif isinstance(hook, SqlHookEntry):
                statements.append(hook.statement)
            elif isinstance(hook, PythonHookEntry):
                continue
            else:
                raise ExecutorInputError(
                    f"{phase_label} hook entry must be a string or typed hook, got {type(hook)}"
                )
        return tuple(statements)
    raise ExecutorInputError(
        f"{phase_label} must be a string, typed hook, or list of hooks, got {type(hooks)}"
    )
