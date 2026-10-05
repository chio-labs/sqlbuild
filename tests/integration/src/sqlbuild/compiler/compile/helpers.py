from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from dataclasses import replace
from itertools import compress
from pathlib import Path
from typing import Any, cast

import pytest

from sqlbuild.cli.commands.main.entrypoint.entry import main
from sqlbuild.compiler.compile._helpers.attachment import core
from sqlbuild.compiler.compile.classes import native_model_rendering
from sqlbuild.compiler.compile.classes.compile_input_reads import CompileInputReads
from sqlbuild.compiler.compile.classes.macro_call_memo import MacroCallMemo
from sqlbuild.compiler.compile.main import _build_compile_inputs
from sqlbuild.compiler.compile.models import (
    CompileModelInput,
    CompilerDiagnostic,
    MemoizedMacroCall,
)
from sqlbuild.compiler.compile.types import NativeReference

type RenderedModels = tuple[object, ...]
type RenderOutcome = tuple[int, dict[str, object], dict[str, bytes], tuple[RenderedModels, ...]]
type NativeRenderComparison = tuple[RenderOutcome, RenderOutcome, dict[str, int]]
type NativeRenderResult = tuple[list[int] | None, list[NativeReference] | None]

_RUN_ID: str = "run-0"
_PROJECT_PLACEHOLDER: str = "<project>"
_OUTCOME_PARTS: tuple[str, ...] = ("exit code", "compile JSON", "compiled SQL", "rendered models")


def use_python_model_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render every model through the authoritative Python path with no macro memo."""

    monkeypatch.setattr(core, "NativeModelRendering", _PythonModelRendering)
    monkeypatch.setattr(
        core._VisibleModelDeclarationCache, "macro_memo_for", lambda self, **kwargs: None
    )


class _PythonModelRendering:
    def __init__(self, **kwargs: object) -> None:
        del kwargs

    def declaration_starts(self, path: Path) -> None:
        del path

    def model_references(self, **kwargs: object) -> None:
        del kwargs

    def record_counts(self) -> None:
        pass


def compare_native_rendering(
    *,
    project_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> NativeRenderComparison:
    """Compile cold through the Python renderer, then through the native renderer."""

    monkeypatch.setattr(
        _build_compile_inputs,
        "resolve_run_id",
        lambda *, selected_run_id: selected_run_id or _RUN_ID,
    )
    with monkeypatch.context() as python_patch:
        use_python_model_rendering(python_patch)
        python: RenderOutcome = _render_outcome(
            project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
        )[0]
    shutil.rmtree(project_dir / "target", ignore_errors=True)
    native: RenderOutcome
    timings: dict[str, int]
    native, timings = _render_outcome(
        project_dir=project_dir, capsys=capsys, monkeypatch=monkeypatch
    )
    return python, native, timings


def render_differences(comparison: NativeRenderComparison) -> tuple[str, ...]:
    """Name every part of the native outcome that differs from the Python outcome."""

    python, native, _ = comparison
    return tuple(compress(_OUTCOME_PARTS, map(lambda left, right: left != right, python, native)))


def rendered_model_counts(comparison: NativeRenderComparison) -> tuple[int, int]:
    """Return how many models the native batch rendered and how many fell back."""

    timings: dict[str, int] = comparison[2]
    return timings.get("model_render_native", 0), timings.get("model_render_fallback", 0)


def _render_outcome(
    *,
    project_dir: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[RenderOutcome, dict[str, int]]:
    rendered: list[RenderedModels] = []
    original: Callable[..., tuple[CompileModelInput, ...]] = (
        _build_compile_inputs.build_model_inputs
    )

    def capture(**kwargs: Any) -> tuple[CompileModelInput, ...]:
        try:
            model_inputs: tuple[CompileModelInput, ...] = original(**kwargs)
        except Exception as error:
            rendered.append((type(error).__name__, str(error)))
            raise
        rendered.append(tuple((item, item.sql_expansion) for item in model_inputs))
        return model_inputs

    with monkeypatch.context() as capture_patch:
        capture_patch.setattr(_build_compile_inputs, "build_model_inputs", capture)
        exit_code: int = main(["--project-dir", str(project_dir), "compile", "--json"])
    output: str = capsys.readouterr().out
    payload: dict[str, object] = json.loads(output.replace(str(project_dir), _PROJECT_PLACEHOLDER))
    timings: dict[str, int] = cast(dict[str, int], payload.pop("compile_timings", {}))
    compiled: Path = project_dir / "target" / "compiled"
    compiled_sql: dict[str, bytes] = {
        path.relative_to(compiled).as_posix(): path.read_bytes() for path in compiled.rglob("*.sql")
    }
    return (exit_code, payload, compiled_sql, tuple(rendered)), timings


def drop_last_declaration_start(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the native scan miss the last declaration reference of every model."""

    _replace_native_results(
        monkeypatch=monkeypatch,
        broken=lambda result: (result[0] and result[0][:-1], result[1]),
    )


def rename_native_references(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the native batch report a different producer for every model reference."""

    _replace_native_results(
        monkeypatch=monkeypatch,
        broken=lambda result: (result[0], result[1] and _renamed_references(result[1])),
    )


def _renamed_references(references: list[NativeReference]) -> list[NativeReference]:
    return [(kind, "orders_000", package, count) for kind, _, package, count in references]


def _replace_native_results(
    *,
    monkeypatch: pytest.MonkeyPatch,
    broken: Callable[[NativeRenderResult], NativeRenderResult],
) -> None:
    original: Callable[[list[str | None], str], list[NativeRenderResult]] = (
        native_model_rendering._native.render_model_sql_batch
    )
    monkeypatch.setattr(
        native_model_rendering._native,
        "render_model_sql_batch",
        lambda sqls, syntax_json: list(map(broken, original(sqls, syntax_json))),
    )


def ignore_dialect_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make native reference extraction read SQL as generic SQL, ignoring dialect comments."""

    monkeypatch.setattr(
        native_model_rendering._native,
        "extract_model_sql_references",
        lambda sql, syntax_json: native_model_rendering._native.extract_static_sql_references(sql),
    )


def replay_stale_macro_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the macro memo replay a call result that differs from the macro's output."""

    original: Callable[..., None] = MacroCallMemo.remember

    def broken(
        self: MacroCallMemo,
        *,
        macro_name: str,
        arguments: str,
        call: MemoizedMacroCall,
        observed: tuple[CompileInputReads, list[tuple[tuple[str, ...], CompilerDiagnostic]]]
        | None = None,
    ) -> None:
        original(
            self,
            macro_name=macro_name,
            arguments=arguments,
            call=replace(call, sql=f"{call.sql} + 0"),
            observed=observed,
        )

    monkeypatch.setattr(MacroCallMemo, "remember", broken)
