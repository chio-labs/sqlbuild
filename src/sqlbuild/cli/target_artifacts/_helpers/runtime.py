"""Write runtime SQL artifacts to target/run."""

from __future__ import annotations

import json
from pathlib import Path

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import LifeCycleEvent
from sqlbuild.adapter.contract.types import LifeCycleEventKind
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.models import (
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SqlTestPlanEntry,
)
from sqlbuild.executor.build.models import BuildExecutionResult, FunctionExecutionResult
from sqlbuild.executor.python_nodes.models import PythonCheckExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from sqlbuild.executor.testing.models import SqlTestExecutionResult

_RUN_DIR: str = "run"
_MODELS_DIR: str = "models"
_FUNCTIONS_DIR: str = "functions"
_TESTS_DIR: str = "tests"
_CHECKS_DIR: str = "checks"
_CHAIN_DIR: str = "_chain_"
_SQL_FILE_SUFFIX: str = ".sql"


def write_runtime_target(
    *,
    target_dir: Path,
    plan_output: PlanOutput,
    result: BuildExecutionResult,
) -> None:
    """Write executed model lifecycle SQL under target/run."""

    run_dir: Path = target_dir / _RUN_DIR

    model_entry_map: dict[str, ModelPlanEntry] = {
        entry.name: entry for entry in plan_output.model_entries
    }
    function_entry_map: dict[str, FunctionPlanEntry] = {
        entry.name: entry for entry in plan_output.function_entries
    }

    model_result: ModelExecutionResult
    for model_result in result.model_results:
        if not model_result.lifecycle_events:
            continue
        sql_events: tuple[LifeCycleEvent, ...] = tuple(
            e for e in model_result.lifecycle_events if e.kind == LifeCycleEventKind.SQL
        )
        if not sql_events:
            continue
        entry: ModelPlanEntry | None = model_entry_map.get(model_result.model_name)
        if entry is None:
            continue
        run_path: Path = run_dir / _model_output_path(entry.relative_path)
        _write_sql(
            path=run_path,
            sql="\n\n".join(_format_statement(e.content) for e in sql_events),
        )

    function_result: FunctionExecutionResult
    for function_result in result.function_results:
        if not function_result.lifecycle_events:
            continue
        function_sql_events: tuple[LifeCycleEvent, ...] = tuple(
            e for e in function_result.lifecycle_events if e.kind == LifeCycleEventKind.SQL
        )
        if not function_sql_events:
            continue
        function_entry: FunctionPlanEntry | None = function_entry_map.get(
            function_result.function_name
        )
        if function_entry is None:
            continue
        function_run_path: Path = run_dir / _function_output_path(
            relative_path=function_entry.relative_path,
            language=function_entry.language,
        )
        _write_sql(
            path=function_run_path,
            sql="\n\n".join(_format_statement(e.content) for e in function_sql_events),
        )


def write_test_runtime_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    plan_output: PlanOutput,
    results: tuple[SqlTestExecutionResult, ...],
) -> None:
    """Write executed SQL unit-test statements under target/run/tests."""

    run_dir: Path = target_dir / _RUN_DIR
    result_keys: frozenset[tuple[str, str | None, int | None, str | None]] = frozenset(
        (
            result.test_name,
            result.source_path.as_posix() if result.source_path is not None else None,
            result.block_index,
            result.case_name,
        )
        for result in results
    )
    entry: SqlTestPlanEntry
    for entry in plan_output.test_entries:
        entry_key: tuple[str, str | None, int | None, str | None] = (
            entry.name,
            entry.source_path.as_posix() if entry.source_path is not None else None,
            entry.block_index,
            entry.case_name,
        )
        if entry_key not in result_keys:
            continue
        test_run_path: Path = run_dir / _TESTS_DIR / _test_output_path(entry)
        _write_sql(
            path=test_run_path,
            sql=build_sql_test_comparison_sql(
                test_entry=entry,
                set_difference_operator=adapter.render_set_difference_operator(),
                sql_analysis_dialect=adapter.sql_analysis_dialect(),
            ),
        )


def write_python_check_runtime_target(
    *, target_dir: Path, results: tuple[PythonCheckExecutionResult, ...]
) -> None:
    """Write Python check runtime results under target/run/checks."""

    if not results:
        return
    run_path: Path = target_dir / _RUN_DIR / _CHECKS_DIR / "python_checks.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {
        "checks": [
            {
                "kind": "python_check",
                "name": result.node_name,
                "display_name": result.node_name,
                "check_id": f"python_check:{result.node_name}",
                "status": "pass" if result.passed else "warn" if result.warned else "fail",
                "passed": result.passed,
                "severity": result.severity.value,
                "message": result.message,
                "error_message": result.error_message,
                "metadata": result.metadata,
            }
            for result in results
        ]
    }
    run_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_sql(*, path: Path, sql: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql.rstrip() + "\n", encoding="utf-8")


def _model_output_path(relative_path: Path) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    if parts and parts[0] == _MODELS_DIR:
        return Path(*parts)
    return Path(_MODELS_DIR) / relative_path


def _function_output_path(*, relative_path: Path, language: FunctionLanguage) -> Path:
    parts: tuple[str, ...] = relative_path.parts
    language_dir: str = language.value
    function_language_path_part_count: int = 2
    if (
        len(parts) >= function_language_path_part_count
        and parts[0] == _FUNCTIONS_DIR
        and parts[1] == language_dir
    ):
        return Path(*parts).with_suffix(_SQL_FILE_SUFFIX)
    return (Path(_FUNCTIONS_DIR) / language_dir / relative_path).with_suffix(_SQL_FILE_SUFFIX)


def _test_output_path(entry: SqlTestPlanEntry) -> Path:
    if entry.case_name is None or entry.source_path is None:
        return _test_folder(entry) / f"{entry.name}{_SQL_FILE_SUFFIX}"
    source_path: Path = entry.source_path.with_suffix("")
    return source_path / f"block_{entry.block_index}__{entry.case_name}{_SQL_FILE_SUFFIX}"


def _test_folder(entry: SqlTestPlanEntry) -> Path:
    model_names: list[str] = [step.model_name for step in entry.chain]
    unique_names: list[str] = sorted(set(model_names))
    if len(unique_names) <= 1:
        return Path(unique_names[0] if unique_names else entry.name)
    return Path(_CHAIN_DIR) / "__".join(unique_names)


def _format_statement(statement: str) -> str:
    stripped: str = statement.rstrip()
    if not stripped:
        return statement
    if stripped.endswith(";"):
        return stripped
    return f"{stripped};"
