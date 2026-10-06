"""Shared builders for render reuse session unit tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

from sqlbuild.compiler.compile._helpers.diagnostics.collector import (
    collect_compile_diagnostics,
    report_compile_diagnostic,
)
from sqlbuild.compiler.compile.classes.render_reuse_session import CompileRenderReuseSession
from sqlbuild.compiler.compile.constants import COMPILE_INPUT_READS
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompilerDiagnostic,
    RenderReuseState,
    StoredRender,
)
from sqlbuild.compiler.compile.types import CompileContextKey, DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import (
    DiscoveredDeclarationFiles,
    DiscoveredMacroFile,
    DiscoveredSqlModelFile,
)
from sqlbuild.compiler.fact_cache.main._load_fact_payload import loaded_fact_payload

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


DECLARATIONS_VARIANT: str = "10"
OTHER_DECLARATIONS_VARIANT: str = "01"


def declaration_files(
    model_files: tuple[DiscoveredSqlModelFile, ...],
) -> DiscoveredDeclarationFiles:
    """Return discovered declaration files holding one macro file and the given models."""

    return DiscoveredDeclarationFiles(
        source_files=(),
        model_files=model_files,
        enum_files=(),
        constant_files=(),
        model_schema_files=(),
        sql_function_files=(),
        sql_hook_files=(),
        python_function_files=(),
        schema_files=(),
        seed_files=(),
        test_files=(),
        scenario_files=(),
        audit_files=(),
        macro_files=(
            DiscoveredMacroFile(
                file_path=Path("/orders/macros/currency.py"),
                relative_path=Path("macros/currency.py"),
                contents="def total(price: str) -> str:\n    return price\n",
            ),
        ),
        adapter_file=None,
    )


class CountingDiscovery:
    """Discover fixed declaration files and count full and model-only discoveries."""

    def __init__(self, model_files: tuple[DiscoveredSqlModelFile, ...]) -> None:
        self.model_files: tuple[DiscoveredSqlModelFile, ...] = model_files
        self.full: int = 0

    def discover(self) -> DiscoveredDeclarationFiles:
        """Discover every declaration file."""

        self.full += 1
        return declaration_files(self.model_files)

    def discover_models(self) -> tuple[DiscoveredSqlModelFile, ...]:
        """Discover model files only."""

        return self.model_files


def declarations_state(*, recorded_variant: str) -> RenderReuseState:
    """Return stored renders of two models, with declaration files discovered for one variant."""

    stored: tuple[DiscoveredSqlModelFile, ...] = (model_file("orders"), model_file("customers"))
    session: CompileRenderReuseSession = CompileRenderReuseSession(prior=None, changed_paths=None)
    _ = session.declaration_files(
        variant=recorded_variant,
        discover=CountingDiscovery(stored).discover,
        discover_models=CountingDiscovery(stored).discover_models,
    )
    session.plan_models(model_files=stored)
    with collect_compile_diagnostics():
        for item in stored:
            _ = session.rendered_model(model_file=item, render=lambda item=item: _render(item))
    state: RenderReuseState | None = session.stored_state()
    assert state is not None
    return state
