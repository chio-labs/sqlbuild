"""Hook execution for model materialization lifecycle."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import StatementRecorder
from sqlbuild.compiler.compile.models.core import CompiledRelationDestination
from sqlbuild.compiler.discovery.models import DiscoveredHookFunction
from sqlbuild.executor.run.models import HookContext, HookExecutionResult, HookRelation
from sqlbuild.executor.run.types import HookPhase
from sqlbuild.executor.shared.exceptions import ExecutorInputError
from sqlbuild.executor.shared.types import ExecutionStatus
from sqlbuild.provider.main.runtime import (
    ProviderContainer,
    _empty_provider_container,
    invoke_with_providers,
)
from sqlbuild.shared.helpers.naming import resolve_destination_qualified_name
from sqlbuild.shared.models import PythonHookEntry, SqlHookEntry


def execute_hooks(
    *,
    connection: Any,
    adapter: BaseAdapter,
    hooks: object,
    phase: HookPhase,
    hook_functions: tuple[DiscoveredHookFunction, ...] = (),
    model_name: str | None = None,
    destination: CompiledRelationDestination | None = None,
    run_id: str = "",
    environment: str | None = None,
    effective_vars: Mapping[str, object] | None = None,
    statement_recorder: StatementRecorder | None = None,
    hook_results: list[HookExecutionResult] | None = None,
    providers: ProviderContainer | None = None,
) -> None:
    """Execute pre/post lifecycle hook entries."""

    if hooks is None:
        return
    if isinstance(hooks, str):
        _execute_sql_hook(
            connection=connection,
            adapter=adapter,
            statement=hooks,
            hook_index=0,
            phase=phase,
            hook_results=hook_results,
        )
        return
    if isinstance(hooks, SqlHookEntry):
        _execute_sql_hook(
            connection=connection,
            adapter=adapter,
            statement=hooks.statement,
            hook_index=0,
            phase=phase,
            hook_results=hook_results,
        )
        return
    if isinstance(hooks, PythonHookEntry):
        invoke_python_hook(
            connection=connection,
            adapter=adapter,
            hook_entry=hooks,
            hook_functions=hook_functions,
            hook_index=0,
            phase=phase,
            model_name=model_name,
            destination=destination,
            run_id=run_id,
            environment=environment,
            effective_vars=effective_vars,
            statement_recorder=statement_recorder,
            hook_results=hook_results,
            providers=providers,
        )
        return
    if isinstance(hooks, list | tuple):
        hook_index: int
        hook: object
        for hook_index, hook in enumerate(hooks):
            if isinstance(hook, str):
                _execute_sql_hook(
                    connection=connection,
                    adapter=adapter,
                    statement=hook,
                    hook_index=hook_index,
                    phase=phase,
                    hook_results=hook_results,
                )
            elif isinstance(hook, SqlHookEntry):
                _execute_sql_hook(
                    connection=connection,
                    adapter=adapter,
                    statement=hook.statement,
                    hook_index=hook_index,
                    phase=phase,
                    hook_results=hook_results,
                )
            elif isinstance(hook, PythonHookEntry):
                invoke_python_hook(
                    connection=connection,
                    adapter=adapter,
                    hook_entry=hook,
                    hook_functions=hook_functions,
                    hook_index=hook_index,
                    phase=phase,
                    model_name=model_name,
                    destination=destination,
                    run_id=run_id,
                    environment=environment,
                    effective_vars=effective_vars,
                    statement_recorder=statement_recorder,
                    hook_results=hook_results,
                    providers=providers,
                )
            else:
                raise ExecutorInputError(
                    f'{phase.value}[{hook_index}] must be sql("...") or python("..."), '
                    f"got {type(hook).__name__}"
                )
        return
    raise ExecutorInputError(
        f'{phase.value} must be a sql("...")/python("...") hook entry or list of hook entries, '
        f"got {type(hooks).__name__}"
    )


def invoke_python_hook(
    *,
    connection: Any,
    adapter: BaseAdapter,
    hook_entry: PythonHookEntry,
    hook_functions: tuple[DiscoveredHookFunction, ...],
    hook_index: int,
    phase: HookPhase,
    model_name: str | None,
    destination: CompiledRelationDestination | None,
    run_id: str,
    environment: str | None,
    effective_vars: Mapping[str, object] | None,
    statement_recorder: StatementRecorder | None,
    hook_results: list[HookExecutionResult] | None = None,
    providers: ProviderContainer | None = None,
) -> None:
    hook_label: str = f'{phase.value}[{hook_index}] python("{hook_entry.name}")'
    hook_function: Callable[..., object] | None = _find_hook_function(
        name=hook_entry.name,
        hook_functions=hook_functions,
    )
    if hook_function is None:
        error_message: str = f"{hook_label} was not found in the runtime hook registry"
        _record_hook_result(
            hook_results=hook_results,
            phase=phase,
            hook_index=hook_index,
            hook_type="python",
            label=hook_entry.name,
            status=ExecutionStatus.FAILED,
            error_message=error_message,
        )
        raise ExecutorInputError(error_message)
    if model_name is None or destination is None:
        error_message = f"{hook_label} is missing runtime model context"
        _record_hook_result(
            hook_results=hook_results,
            phase=phase,
            hook_index=hook_index,
            hook_type="python",
            label=hook_entry.name,
            status=ExecutionStatus.FAILED,
            error_message=error_message,
        )
        raise ExecutorInputError(error_message)

    context: HookContext = build_hook_context(
        connection=connection,
        adapter=adapter,
        hook_entry=hook_entry,
        hook_index=hook_index,
        phase=phase,
        model_name=model_name,
        destination=destination,
        run_id=run_id,
        environment=environment,
        effective_vars=effective_vars or {},
        statement_recorder=statement_recorder or StatementRecorder(),
        providers=providers or _empty_provider_container(),
    )
    try:
        invoke_with_providers(
            function=hook_function,
            context=context,
            providers=providers,
            supplied_kwargs=dict(hook_entry.kwargs),
        )
    except Exception as exc:
        error_message: str = f"{hook_label} failed: {exc}"
        _record_hook_result(
            hook_results=hook_results,
            phase=phase,
            hook_index=hook_index,
            hook_type="python",
            label=hook_entry.name,
            status=ExecutionStatus.FAILED,
            error_message=error_message,
        )
        raise ExecutorInputError(error_message) from exc
    _record_hook_result(
        hook_results=hook_results,
        phase=phase,
        hook_index=hook_index,
        hook_type="python",
        label=hook_entry.name,
        status=ExecutionStatus.SUCCESS,
    )


def _execute_sql_hook(
    *,
    connection: Any,
    adapter: BaseAdapter,
    statement: str,
    hook_index: int,
    phase: HookPhase,
    hook_results: list[HookExecutionResult] | None,
) -> None:
    try:
        adapter.execute(connection, statement)
    except Exception as exc:
        _record_hook_result(
            hook_results=hook_results,
            phase=phase,
            hook_index=hook_index,
            hook_type="sql",
            label=_sql_hook_preview(statement),
            status=ExecutionStatus.FAILED,
            error_message=str(exc),
        )
        raise
    _record_hook_result(
        hook_results=hook_results,
        phase=phase,
        hook_index=hook_index,
        hook_type="sql",
        label=_sql_hook_preview(statement),
        status=ExecutionStatus.SUCCESS,
    )


def _record_hook_result(
    *,
    hook_results: list[HookExecutionResult] | None,
    phase: HookPhase,
    hook_index: int,
    hook_type: str,
    label: str,
    status: ExecutionStatus,
    error_message: str | None = None,
) -> None:
    if hook_results is None:
        return
    hook_results.append(
        HookExecutionResult(
            phase=phase,
            index=hook_index,
            hook_type=hook_type,
            label=label,
            status=status,
            error_message=error_message,
        )
    )


def _sql_hook_preview(statement: str) -> str:
    normalized: str = " ".join(statement.split())
    if len(normalized) <= 80:
        return normalized
    return normalized[:77] + "..."


def build_hook_context(
    *,
    connection: Any,
    adapter: BaseAdapter,
    hook_entry: PythonHookEntry,
    hook_index: int,
    phase: HookPhase,
    model_name: str,
    destination: CompiledRelationDestination,
    run_id: str,
    environment: str | None,
    effective_vars: Mapping[str, object],
    statement_recorder: StatementRecorder,
    providers: ProviderContainer,
) -> HookContext:
    relation: HookRelation = HookRelation(
        name=destination.name,
        schema=destination.schema,
        database=destination.database,
        qualified=resolve_destination_qualified_name(adapter=adapter, target=destination),
    )
    return HookContext(
        model_name=model_name,
        phase=phase,
        hook_name=hook_entry.name,
        hook_index=hook_index,
        run_id=run_id,
        environment=environment,
        vars=effective_vars,
        target=relation,
        destination=relation,
        adapter_name=adapter.adapter_name,
        adapter=adapter,
        connection=connection,
        statement_recorder=statement_recorder,
        providers=providers,
    )


def _find_hook_function(
    *, name: str, hook_functions: tuple[DiscoveredHookFunction, ...]
) -> Callable[..., object] | None:
    hook_function: DiscoveredHookFunction
    for hook_function in hook_functions:
        if hook_function.name == name:
            return hook_function.function
    return None


def render_hooks(*, hooks: object, phase: HookPhase) -> tuple[str, ...]:
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
                    f'{phase.value}[{hook_index}] must be sql("...") or python("..."), '
                    f"got {type(hook).__name__}"
                )
        return tuple(statements)
    raise ExecutorInputError(
        f'{phase.value} must be a sql("...")/python("...") hook entry or list of hook entries, '
        f"got {type(hooks).__name__}"
    )
