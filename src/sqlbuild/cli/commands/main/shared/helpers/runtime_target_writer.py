"""Write runtime SQL artifacts to target/run."""

from __future__ import annotations

from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.models import (
    FunctionPlanEntry,
    ModelPlanEntry,
    PlanOutput,
    SqlTestPlanEntry,
)
from sqlbuild.executor.build.models import BuildExecutionResult, FunctionExecutionResult
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.executor.testing.main.comparison_sql import build_sql_test_comparison_sql
from sqlbuild.executor.testing.models import SqlTestExecutionResult

_RUN_DIR: str = "run"
_MODELS_DIR: str = "models"
_FUNCTIONS_DIR: str = "functions"
_TESTS_DIR: str = "tests"
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
    result_names: frozenset[str] = frozenset(result.test_name for result in results)
    entry: SqlTestPlanEntry
    for entry in plan_output.test_entries:
        if entry.name not in result_names:
            continue
        test_run_path: Path = run_dir / _TESTS_DIR / _test_folder(entry) / f"{entry.name}.sql"
        _write_sql(
            path=test_run_path,
            sql=build_sql_test_comparison_sql(
                entry,
                set_difference_operator=adapter.render_set_difference_operator(),
                sqlglot_dialect=adapter.sqlglot_dialect(),
            ),
        )


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
    if len(parts) >= 2 and parts[0] == _FUNCTIONS_DIR and parts[1] == language_dir:
        return Path(*parts).with_suffix(_SQL_FILE_SUFFIX)
    return (Path(_FUNCTIONS_DIR) / language_dir / relative_path).with_suffix(_SQL_FILE_SUFFIX)


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
