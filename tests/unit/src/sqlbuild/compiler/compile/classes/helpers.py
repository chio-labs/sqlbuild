"""Shared builders for render reuse session and macro call memo unit tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    collect_compile_diagnostics,
    report_compile_diagnostic,
)
from sqlbuild.compiler.compile._helpers.macro_memo.call_reads import observed_macro_call
from sqlbuild.compiler.compile.classes.macro_call_memo import MacroCallMemo
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompilerDiagnostic,
    MemoizedMacroCall,
    RenderReuseState,
    StoredRender,
)
from sqlbuild.compiler.compile.types import CompileContextKey, DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile
from sqlbuild.compiler.fact_cache.main._load_fact_payload import loaded_fact_payload
from sqlbuild.compiler.scopes.models import ResourceIdentity
from sqlbuild.compiler.scopes.types import ResourceKind

REGION_ENV_VAR: str = "ORDERS_REGION"


def model_file(name: str, sql: str = "SELECT 1 AS order_id") -> DiscoveredSqlModelFile:
    """Return one discovered SQL model."""

    return DiscoveredSqlModelFile(
        file_path=Path("/orders") / "models" / f"{name}.sql",
        relative_path=Path("models") / f"{name}.sql",
        contents=sql,
        header_values={},
        header_column_locations={},
        output_column_locations={},
        query_sql=sql,
    )


def missing_description(name: str) -> CompilerDiagnostic:
    """Return the warning a render of the named model reports."""

    return CompilerDiagnostic(
        phase=DiagnosticPhase.COMPILE,
        severity=DiagnosticSeverity.WARNING,
        code="P010",
        message=f"Model '{name}' has no description",
    )


def _render(item: DiscoveredSqlModelFile) -> CompileModelInput:
    report_compile_diagnostic(
        key=(item.file_path.stem,), diagnostic=missing_description(item.file_path.stem)
    )
    COMPILE_INPUT_READS.environment_read(REGION_ENV_VAR)
    return CompileModelInput(model_file=item, query_sql=item.query_sql)


def _render_reading_run_id(item: DiscoveredSqlModelFile) -> CompileModelInput:
    COMPILE_INPUT_READS.context_read(CompileContextKey.RUN_ID)
    return _render(item)


def recorded_state(
    model_files: tuple[DiscoveredSqlModelFile, ...],
    *,
    run_id_readers: frozenset[str] = frozenset(),
) -> RenderReuseState:
    """Render every model through a fresh session and return what it stores."""

    session: CompileRenderReuseSession = CompileRenderReuseSession(prior=None, changed_paths=None)
    session.plan_models(model_files=model_files)
    renderers: dict[bool, Callable[[DiscoveredSqlModelFile], CompileModelInput]] = {
        False: _render,
        True: _render_reading_run_id,
    }
    with collect_compile_diagnostics():
        for item in model_files:
            render: Callable[[DiscoveredSqlModelFile], CompileModelInput] = renderers[
                item.file_path.stem in run_id_readers
            ]
            _ = session.rendered_model(model_file=item, render=lambda item=item, r=render: r(item))
    state: RenderReuseState | None = session.stored_state()
    assert state is not None
    return state


def planned_session(
    *,
    stored: tuple[DiscoveredSqlModelFile, ...],
    current: tuple[DiscoveredSqlModelFile, ...],
    changed_paths: frozenset[str] = frozenset(),
    run_id_readers: frozenset[str] = frozenset(),
) -> CompileRenderReuseSession:
    """Record renders for the stored models, then plan a session for the current models."""

    session: CompileRenderReuseSession = CompileRenderReuseSession(
        prior=recorded_state(stored, run_id_readers=run_id_readers), changed_paths=changed_paths
    )
    session.plan_models(model_files=current)
    return session


def corrupted_session(item: DiscoveredSqlModelFile) -> CompileRenderReuseSession:
    """Plan a session whose only stored render payload cannot be decoded."""

    state: RenderReuseState = recorded_state((item,))
    session: CompileRenderReuseSession = CompileRenderReuseSession(
        prior=replace(
            state,
            model_payloads={str(item.relative_path): memoryview(b"not a render")},
        ),
        changed_paths=frozenset(),
    )
    session.plan_models(model_files=(item,))
    return session


def edited_session(*, retained_models: frozenset[str]) -> CompileRenderReuseSession:
    """Reuse the stored orders render and render an edited customers model."""

    orders: DiscoveredSqlModelFile = model_file("orders")
    customers: DiscoveredSqlModelFile = model_file("customers", "SELECT 2 AS customer_id")
    session: CompileRenderReuseSession = CompileRenderReuseSession(
        prior=recorded_state((orders, model_file("customers"))),
        changed_paths=frozenset({str(customers.relative_path)}),
        retained_models=retained_models,
    )
    session.plan_models(model_files=(orders, customers))
    with collect_compile_diagnostics():
        _ = session.reused_model(model_file=orders)
        _ = session.rendered_model(model_file=customers, render=lambda: _render(customers))
    return session


def released_paths(state: RenderReuseState | None) -> dict[str, bool]:
    """Return, per stored model, whether its bytes were released."""

    assert state is not None
    return {path: payload is None for path, payload in state.model_payloads.items()}


def stored_query_sqls(state: RenderReuseState | None) -> dict[str, str]:
    """Decode every stored model render and return its query SQL."""

    assert state is not None
    return {
        path: _stored_query_sql(cast(memoryview, payload))
        for path, payload in filter(lambda item: item[1] is not None, state.model_payloads.items())
    }


def _stored_query_sql(payload: memoryview) -> str:
    stored: StoredRender = cast(StoredRender, loaded_fact_payload(payload))
    return cast(CompileModelInput, stored.value).query_sql


def macro_call_without_reads() -> None:
    """Stand in for a macro call that reads no volatile input."""


def macro_call_reading_environment() -> None:
    """Stand in for a macro call that reads two environment variables."""

    COMPILE_INPUT_READS.environment_read(REGION_ENV_VAR)
    COMPILE_INPUT_READS.environment_read("ORDERS_CURRENCY")


def macro_call_reading_run_id() -> None:
    """Stand in for a macro call that reads the per-invocation run identity."""

    COMPILE_INPUT_READS.context_read(CompileContextKey.RUN_ID)


def macro_call_reporting_diagnostic() -> None:
    """Stand in for a macro call that reads the environment and reports a diagnostic."""

    COMPILE_INPUT_READS.environment_read(REGION_ENV_VAR)
    report_compile_diagnostic(
        key=("P010", "orders_summary"), diagnostic=missing_description("orders_summary")
    )


def remembered_macro_call(
    macro_call: Callable[[], None],
) -> dict[str, MemoizedMacroCall] | None:
    """Observe one stand-in macro call, offer it to a fresh memo, and return what it kept."""

    memo: MacroCallMemo = MacroCallMemo()
    with collect_compile_diagnostics(), observed_macro_call() as observed:
        macro_call()
    memo.remember(
        macro_name="orders_sql",
        arguments="'amount'",
        call=MemoizedMacroCall(
            sql="CAST(amount AS BIGINT)",
            consumer=ResourceIdentity(ResourceKind.MODEL, "orders_summary"),
            dependencies=(),
            usages=(),
            call_site_refs=(),
        ),
        observed=observed,
    )
    return memo.calls_for("orders_sql")
