"""Shared builders for render reuse session unit tests."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

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
)
from sqlbuild.compiler.compile.types import CompileContextKey, DiagnosticPhase, DiagnosticSeverity
from sqlbuild.compiler.discovery.models import DiscoveredSqlModelFile

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
    session.renders_complete()
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
