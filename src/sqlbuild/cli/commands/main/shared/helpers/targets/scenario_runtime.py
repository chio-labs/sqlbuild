"""Write scenario runtime SQL artifacts to target/run."""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import LifeCycleEvent
from sqlbuild.adapter.shared.types import LifeCycleEventKind
from sqlbuild.compiler.compile.types import FunctionLanguage
from sqlbuild.compiler.planner.models import FunctionPlanEntry, ScenarioExecutionPlan
from sqlbuild.executor.scenario.models import (
    ScenarioCleanupExecutionResult,
    ScenarioLocalSnapshotLoadedRelation,
    ScenarioRunResult,
)
from sqlbuild.shared.helpers.naming import resolve_relation_location_qualified_name
from sqlbuild.shared.helpers.scenario_expected_comparison_sql import (
    build_scenario_expected_comparison_sql,
)

_RUN_DIR: str = "run"
_SCENARIOS_DIR: str = "scenarios"
_FIXTURES_DIR: str = "fixtures"
_FUNCTIONS_DIR: str = "functions"
_SEEDS_DIR: str = "seeds"
_MODELS_DIR: str = "models"
_EXPECTATIONS_DIR: str = "expectations"
_CLEANUP_DIR: str = "cleanup"
_LOCAL_DIR: str = "local"
_SQL_FILE_SUFFIX: str = ".sql"


def write_scenario_runtime_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    scenario_plan: ScenarioExecutionPlan,
    result: ScenarioRunResult,
) -> None:
    """Write executed scenario lifecycle SQL under target/run/scenarios."""

    scenario_run_dir: Path = target_dir / _RUN_DIR / _SCENARIOS_DIR / scenario_plan.name
    if scenario_run_dir.exists():
        shutil.rmtree(scenario_run_dir)

    _write_cleanup_result(
        scenario_run_dir=scenario_run_dir,
        file_name="prepare.sql",
        cleanup_result=result.prepare_cleanup_result,
    )

    for fixture_result in result.fixture_results:
        sql: str = _sql_events_text(fixture_result.lifecycle_events)
        if not sql:
            continue
        fixture_path: Path = (
            scenario_run_dir
            / _FIXTURES_DIR
            / f"{fixture_result.kind.value}__{_safe_file_stem(fixture_result.logical_name)}.sql"
        )
        _write_sql(path=fixture_path, sql=sql)

    for seed_result in result.seed_results:
        sql = _sql_events_text(seed_result.lifecycle_events)
        if not sql:
            continue
        seed_path: Path = scenario_run_dir / _SEEDS_DIR / f"{seed_result.seed_name}.sql"
        _write_sql(path=seed_path, sql=sql)

    for model_result in result.model_results:
        sql = _sql_events_text(model_result.lifecycle_events)
        if not sql:
            continue
        relative_path: Path | None = _model_relative_path(
            scenario_plan=scenario_plan,
            model_name=model_result.model_name,
        )
        if relative_path is None:
            continue
        model_path: Path = scenario_run_dir / _model_output_path(relative_path)
        _write_sql(path=model_path, sql=sql)

    for expected_expectation in scenario_plan.expected_expectations:
        expected_path: Path = (
            scenario_run_dir
            / _EXPECTATIONS_DIR
            / f"expected__{expected_expectation.model_name}.sql"
        )
        actual_relation: str = resolve_relation_location_qualified_name(
            adapter=adapter,
            location=expected_expectation.actual_destination,
        )
        _write_sql(
            path=expected_path,
            sql=build_scenario_expected_comparison_sql(
                actual_sql=f"SELECT * FROM {actual_relation}",
                expected_sql=expected_expectation.expected_sql,
                set_difference_operator=adapter.render_set_difference_operator(),
            ),
        )

    for assertion_expectation in scenario_plan.assertion_expectations:
        assertion_path: Path = (
            scenario_run_dir / _EXPECTATIONS_DIR / f"assertion__{assertion_expectation.name}.sql"
        )
        _write_sql(
            path=assertion_path,
            sql=(
                "SELECT COUNT(*) FROM "
                f"({assertion_expectation.sql}) AS __scenario_assertion_failures;\n\n"
                "SELECT * FROM "
                f"({assertion_expectation.sql}) AS __scenario_assertion_failures\n"
                "LIMIT 10;"
            ),
        )

    _write_cleanup_result(
        scenario_run_dir=scenario_run_dir,
        file_name="final.sql",
        cleanup_result=result.cleanup_result,
    )


def write_local_scenario_runtime_target(
    *,
    target_dir: Path,
    adapter: BaseAdapter,
    scenario_plan: ScenarioExecutionPlan,
    result: ScenarioRunResult,
) -> None:
    """Write local scenario replay SQL/debug artifacts under target/run/scenarios."""

    local_plan: ScenarioExecutionPlan = result.local_execution_plan or scenario_plan
    scenario_run_dir: Path = target_dir / _RUN_DIR / _SCENARIOS_DIR / scenario_plan.name
    local_run_dir: Path = scenario_run_dir / _LOCAL_DIR
    if local_run_dir.exists():
        shutil.rmtree(local_run_dir)

    _write_local_fixture_artifacts(
        local_run_dir=local_run_dir,
        loaded_relations=result.local_snapshot_relations,
    )
    _write_local_function_artifacts(
        local_run_dir=local_run_dir,
        adapter=adapter,
        scenario_plan=local_plan,
        result=result,
    )
    _write_local_model_artifacts(local_run_dir=local_run_dir, scenario_plan=local_plan)
    _write_local_expectation_artifacts(
        local_run_dir=local_run_dir,
        adapter=adapter,
        scenario_plan=local_plan,
    )


def _write_cleanup_result(
    *,
    scenario_run_dir: Path,
    file_name: str,
    cleanup_result: ScenarioCleanupExecutionResult | None,
) -> None:
    if cleanup_result is None:
        return
    sql: str = _sql_events_text(cleanup_result.lifecycle_events)
    if not sql:
        return
    _write_sql(path=scenario_run_dir / _CLEANUP_DIR / file_name, sql=sql)


def _write_local_fixture_artifacts(
    *, local_run_dir: Path, loaded_relations: tuple[ScenarioLocalSnapshotLoadedRelation, ...]
) -> None:
    loaded_relation: ScenarioLocalSnapshotLoadedRelation
    for loaded_relation in loaded_relations:
        fixture_path: Path = (
            local_run_dir
            / _FIXTURES_DIR
            / f"{loaded_relation.kind.value}__{_safe_file_stem(loaded_relation.logical_name)}.sql"
        )
        _write_sql(
            path=fixture_path,
            sql=(
                f"-- loaded from {loaded_relation.file_path.as_posix()}\n"
                f"-- rows: {loaded_relation.row_count}\n"
                f'CREATE TABLE "{loaded_relation.table_name}" AS SELECT * FROM '
                f"'{loaded_relation.file_path.as_posix()}';"
            ),
        )


def _write_local_function_artifacts(
    *,
    local_run_dir: Path,
    adapter: BaseAdapter,
    scenario_plan: ScenarioExecutionPlan,
    result: ScenarioRunResult,
) -> None:
    executed_function_names: frozenset[str] = frozenset(
        function_result.function_name for function_result in result.function_results
    )
    function_entry: FunctionPlanEntry
    for function_entry in scenario_plan.function_entries:
        if function_entry.name not in executed_function_names:
            continue
        function_path: Path = local_run_dir / _function_output_path(
            relative_path=function_entry.relative_path,
            language=function_entry.language,
        )
        _write_sql(
            path=function_path,
            sql="\n\n".join(
                _format_statement(statement)
                for statement in adapter.render_create_function(
                    destination=function_entry.destination.qualified_name
                    or function_entry.destination.name,
                    arguments=function_entry.arguments,
                    returns=function_entry.returns,
                    body_sql=function_entry.body_sql,
                    return_columns=function_entry.return_columns,
                    language=function_entry.language,
                    runtime_version=function_entry.runtime_version,
                    entry_point=function_entry.entry_point,
                    packages=function_entry.packages,
                )
            ),
        )


def _write_local_model_artifacts(
    *, local_run_dir: Path, scenario_plan: ScenarioExecutionPlan
) -> None:
    for entry in scenario_plan.model_entries:
        model_path: Path = local_run_dir / _model_output_path(entry.relative_path)
        _write_sql(path=model_path, sql=entry.resolved_sql)


def _write_local_expectation_artifacts(
    *, local_run_dir: Path, adapter: BaseAdapter, scenario_plan: ScenarioExecutionPlan
) -> None:
    for expected_expectation in scenario_plan.expected_expectations:
        expected_path: Path = (
            local_run_dir / _EXPECTATIONS_DIR / f"expected__{expected_expectation.model_name}.sql"
        )
        actual_relation: str = resolve_relation_location_qualified_name(
            adapter=adapter,
            location=expected_expectation.actual_destination,
        )
        _write_sql(
            path=expected_path,
            sql=build_scenario_expected_comparison_sql(
                actual_sql=f"SELECT * FROM {actual_relation}",
                expected_sql=expected_expectation.expected_sql,
                set_difference_operator=adapter.render_set_difference_operator(),
            ),
        )
    for assertion_expectation in scenario_plan.assertion_expectations:
        assertion_path: Path = (
            local_run_dir / _EXPECTATIONS_DIR / f"assertion__{assertion_expectation.name}.sql"
        )
        _write_sql(
            path=assertion_path,
            sql=(
                "SELECT COUNT(*) FROM "
                f"({assertion_expectation.sql}) AS __scenario_assertion_failures;\n\n"
                "SELECT * FROM "
                f"({assertion_expectation.sql}) AS __scenario_assertion_failures\n"
                "LIMIT 10;"
            ),
        )


def _sql_events_text(events: tuple[LifeCycleEvent, ...]) -> str:
    sql_events: tuple[LifeCycleEvent, ...] = tuple(
        event for event in events if event.kind == LifeCycleEventKind.SQL
    )
    return "\n\n".join(_format_statement(event.content) for event in sql_events)


def _model_relative_path(*, scenario_plan: ScenarioExecutionPlan, model_name: str) -> Path | None:
    for entry in scenario_plan.model_entries:
        if entry.name == model_name:
            return entry.relative_path
    return None


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


def _safe_file_stem(name: str) -> str:
    return name.replace("/", "__").replace("\\", "__")


def _write_sql(*, path: Path, sql: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(sql.rstrip() + "\n", encoding="utf-8")


def _format_statement(statement: str) -> str:
    stripped: str = statement.rstrip()
    if not stripped:
        return statement
    if stripped.endswith(";"):
        return stripped
    return f"{stripped};"
