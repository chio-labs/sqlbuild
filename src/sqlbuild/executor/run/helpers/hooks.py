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
    """Execute pre/post lifecycle hook entries."""

    if hooks is None:
        return
    if isinstance(hooks, str):
        adapter.execute(connection, hooks)
        return
    if isinstance(hooks, SqlHookEntry):
        adapter.execute(connection, hooks.statement)
        return
    if isinstance(hooks, PythonHookEntry):
        raise ExecutorInputError(
            f'{phase_label} python("{hooks.name}") is valid at compile time, '
            "but Python hook execution is not implemented yet"
        )
    if isinstance(hooks, list | tuple):
        hook_index: int
        hook: object
        for hook_index, hook in enumerate(hooks):
            if isinstance(hook, str):
                adapter.execute(connection, hook)
            elif isinstance(hook, SqlHookEntry):
                adapter.execute(connection, hook.statement)
            elif isinstance(hook, PythonHookEntry):
                raise ExecutorInputError(
                    f'{phase_label}[{hook_index}] python("{hook.name}") is valid at compile time, '
                    "but Python hook execution is not implemented yet"
                )
            else:
                raise ExecutorInputError(
                    f'{phase_label}[{hook_index}] must be sql("...") or python("..."), '
                    f"got {type(hook).__name__}"
                )
        return
    raise ExecutorInputError(
        f'{phase_label} must be a sql("...")/python("...") hook entry or list of hook entries, '
        f"got {type(hooks).__name__}"
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
        hook_index: int
        hook: object
        for hook_index, hook in enumerate(hooks):
            if isinstance(hook, str):
                statements.append(hook)
            elif isinstance(hook, SqlHookEntry):
                statements.append(hook.statement)
            elif isinstance(hook, PythonHookEntry):
                continue
            else:
                raise ExecutorInputError(
                    f'{phase_label}[{hook_index}] must be sql("...") or python("..."), '
                    f"got {type(hook).__name__}"
                )
        return tuple(statements)
    raise ExecutorInputError(
        f'{phase_label} must be a sql("...")/python("...") hook entry or list of hook entries, '
        f"got {type(hooks).__name__}"
    )
