"""Scenario command runner."""

from __future__ import annotations

import sys
from pathlib import Path
from time import monotonic
from typing import Any, TextIO, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.scenario.constants import FAILED_STATUS, SUCCESS_STATUS
from sqlbuild.cli.commands.main.shared.exceptions import CliUserError
from sqlbuild.cli.commands.main.shared.helpers.adapters import resolve_adapter
from sqlbuild.cli.commands.main.shared.helpers.connection import resolve_project_connection_config
from sqlbuild.cli.commands.main.shared.helpers.connection_progress import ConnectionProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.planning_progress import PlanningProgressReporter
from sqlbuild.cli.commands.main.shared.helpers.progress import format_build_header
from sqlbuild.cli.commands.main.shared.helpers.scenario_runtime_target_writer import (
    write_scenario_runtime_target,
)
from sqlbuild.cli.commands.main.shared.helpers.status import TransientStatusReporter
from sqlbuild.compiler.compile.models import CompiledProject, CompiledSqlScenario
from sqlbuild.compiler.discovery.main.discover import discover_project_inputs
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline.main.compile import run_compile_pipeline
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.main.scenario import build_scenario_plan
from sqlbuild.compiler.planner.models import ScenarioArtifactName, ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.main.run import execute_scenario_run
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionCheckExecutionResult,
    ScenarioExpectedCheckExecutionResult,
    ScenarioRunResult,
)
from sqlbuild.shared.helpers.colors import (
    blue_bold,
    colorize_status,
    dim,
    green_bold,
    supports_color,
)
from sqlbuild.spec.models.project import resolve_effective_adapter_name

_SCENARIO_NAME_WIDTH: int = 64
_CHECK_LABEL_WIDTH: int = 10
_CHECK_NAME_WIDTH: int = 50


def run_scenario(
    project_dir: Path | None,
    no_sql_validation: bool = False,
    no_color: bool = False,
    selector: str | None = None,
    retain: bool = False,
) -> int:
    """Execute the scenario test command."""

    effective_project_dir: Path = project_dir if project_dir is not None else Path.cwd()
    discovered_inputs: DiscoveredProjectInputs = discover_project_inputs(
        project_dir=effective_project_dir
    )
    adapter_name: str = resolve_effective_adapter_name(
        project_config=discovered_inputs.project_config,
        local_config=discovered_inputs.local_config,
    )
    adapter: BaseAdapter = resolve_adapter(adapter_name, project_dir=effective_project_dir)
    connection_config: dict[str, object] = resolve_project_connection_config(
        discovered_inputs=discovered_inputs,
        project_dir=effective_project_dir,
    )
    use_color: bool = not no_color and supports_color()
    progress_stream: TextIO = sys.stdout
    execution_header: str = format_build_header(
        command="sqb scenario test", target=selector, concurrency=1
    )
    execution_label: str = blue_bold("Execution") if use_color else "Execution"
    header_detail: str = dim(execution_header) if use_color else execution_header
    connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )
    planning_progress: PlanningProgressReporter = PlanningProgressReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    progress_stream.write(f"\n{execution_label}  {header_detail}\n\n")
    progress_stream.flush()

    pipeline_result: CompilePipelineResult = run_compile_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=adapter,
        no_sql_validation=no_sql_validation,
        connection_config=connection_config,
        on_connection_start=connection_progress.on_connection_start,
        on_connection_complete=connection_progress.on_connection_complete,
        on_connection_error=connection_progress.on_connection_error,
        on_progress=planning_progress.on_progress,
    )
    scenarios: tuple[CompiledSqlScenario, ...] = _select_scenarios(
        project=pipeline_result.project,
        selector=selector,
        project_dir=effective_project_dir,
    )
    header: str = f"Scenario ({len(scenarios)} selected)"
    styled_header: str = green_bold(header) if use_color else header
    progress_stream.write(f"\n{styled_header}\n\n")
    progress_stream.flush()
    scenario_status: TransientStatusReporter = TransientStatusReporter(
        stream=progress_stream,
        use_color=use_color,
    )
    execution_connection_progress: ConnectionProgressReporter = ConnectionProgressReporter(
        adapter_name=adapter_name,
        stream=progress_stream,
        use_color=use_color,
    )

    execution_connection_progress.on_connection_start(1)
    connection_start: float = monotonic()
    connection: Any
    try:
        connection = adapter.connect(connection_config)
    except Exception:
        execution_connection_progress.on_connection_error(1, monotonic() - connection_start)
        raise
    execution_connection_progress.on_connection_complete(1, monotonic() - connection_start)
    results: list[ScenarioRunResult] = []
    status_is_tty: bool = hasattr(progress_stream, "isatty") and progress_stream.isatty()
    if not status_is_tty:
        progress_stream.write("Running scenarios...\n\n")
        progress_stream.flush()
    try:
        scenario: CompiledSqlScenario
        for scenario in scenarios:
            if status_is_tty:
                scenario_status.start("Running scenarios...")
            result: ScenarioRunResult = _run_one_scenario(
                scenario=scenario,
                pipeline_result=pipeline_result,
                adapter=adapter,
                connection=connection,
                project_name=discovered_inputs.project_config.name,
                target_dir=effective_project_dir / "target",
                retain=retain,
            )
            if status_is_tty:
                scenario_status.close()
            results.append(result)
            _write_scenario_result(result=result, stream=progress_stream, use_color=use_color)
    finally:
        scenario_status.close()
        adapter.close(connection)

    pass_count: int = sum(1 for result in results if result.status == SUCCESS_STATUS)
    fail_count: int = len(results) - pass_count
    progress_stream.write(f"\nPASS={pass_count}  FAIL={fail_count}  TOTAL={len(results)}\n")
    progress_stream.flush()
    return 0 if fail_count == 0 else 1


def _select_scenarios(
    *, project: CompiledProject, selector: str | None, project_dir: Path
) -> tuple[CompiledSqlScenario, ...]:
    if selector is None:
        if not project.sql_scenarios:
            raise CliUserError(
                "No SQL scenarios were discovered under tests/scenarios", code="C451"
            )
        return project.sql_scenarios

    selector_path: Path = Path(selector)
    matches: list[CompiledSqlScenario] = []
    scenario: CompiledSqlScenario
    for scenario in project.sql_scenarios:
        if scenario.name == selector:
            matches.append(scenario)
            continue
        scenario_path: Path = scenario.scenario_file.file_path
        if selector_path.suffix == ".sql" and (
            scenario_path == selector_path
            or scenario_path == project_dir / selector_path
            or scenario.scenario_file.relative_path == selector_path
        ):
            matches.append(scenario)
    if len(matches) == 1:
        return (matches[0],)
    if len(matches) > 1:
        raise CliUserError(
            f"Scenario selector '{selector}' matched multiple scenarios", code="C452"
        )
    raise CliUserError(f"Unknown scenario selector '{selector}'", code="C453")


def _run_one_scenario(
    *,
    scenario: CompiledSqlScenario,
    pipeline_result: CompilePipelineResult,
    adapter: BaseAdapter,
    connection: Any,
    project_name: str,
    target_dir: Path,
    retain: bool,
) -> ScenarioRunResult:
    try:
        scenario_plan: ScenarioExecutionPlan = build_scenario_plan(
            scenario=scenario,
            pipeline_result=pipeline_result,
            adapter=adapter,
            project_name=project_name,
        )
        result: ScenarioRunResult = execute_scenario_run(
            scenario_plan=scenario_plan,
            adapter=adapter,
            connection=connection,
            run_id=pipeline_result.project.run_id,
            retain=retain,
        )
        write_scenario_runtime_target(
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
        )
        return result
    except Exception as exc:
        return ScenarioRunResult(
            scenario_name=scenario.name,
            status=cast(Any, FAILED_STATUS),
            retained=retain,
            error_message=str(exc),
        )


def _write_scenario_result(*, result: ScenarioRunResult, stream: TextIO, use_color: bool) -> None:
    status_text: str = "PASS" if result.status == SUCCESS_STATUS else "FAIL"
    status: str = colorize_status(status_text, use_color=use_color)
    stream.write(f"{result.scenario_name:<{_SCENARIO_NAME_WIDTH}} {status}\n")
    if result.error_message:
        error_line: str
        for error_line in result.error_message.splitlines():
            stream.write(f"    {error_line}\n")
        if not result.retained:
            stream.write("    Rerun with --retain to inspect scenario-owned artifacts.\n")
    _write_checks(result=result, stream=stream, use_color=use_color)
    if result.retained and result.relation_map is not None:
        stream.write("    Retained relations:\n")
        artifact: ScenarioArtifactName
        for artifact in result.relation_map.artifacts:
            kind: str = ScenarioArtifactKind(artifact.identity.kind).value
            stream.write(
                f"      {kind:<6} {artifact.identity.logical_name} -> {artifact.physical_name}\n"
            )
    _write_check_failures(result=result, stream=stream)
    stream.flush()


def _write_checks(*, result: ScenarioRunResult, stream: TextIO, use_color: bool) -> None:
    expected: ScenarioExpectedCheckExecutionResult
    for expected in result.expected_results:
        status_text: str = "FAIL" if expected.status == FAILED_STATUS else "PASS"
        status: str = colorize_status(status_text, use_color=use_color)
        detail: str = ""
        if expected.status == FAILED_STATUS:
            detail = f"  {expected.mismatched_row_count} mismatched"
        item_name: str = f"expected {expected.model_name}"
        stream.write(
            f"    {'check':<{_CHECK_LABEL_WIDTH}}{item_name:<{_CHECK_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )
        if expected.error_message is not None:
            stream.write(f"{'':>14}{expected.error_message}\n")
    assertion: ScenarioAssertionCheckExecutionResult
    for assertion in result.assertion_results:
        status_text = "FAIL" if assertion.status == FAILED_STATUS else "PASS"
        status = colorize_status(status_text, use_color=use_color)
        row_label: str = "row" if assertion.failing_row_count == 1 else "rows"
        detail = ""
        if assertion.status == FAILED_STATUS:
            detail = f"  {assertion.failing_row_count} {row_label}"
        item_name = f"assertion {assertion.name}"
        stream.write(
            f"    {'check':<{_CHECK_LABEL_WIDTH}}{item_name:<{_CHECK_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )
        if assertion.error_message is not None:
            stream.write(f"{'':>14}{assertion.error_message}\n")


def _write_check_failures(*, result: ScenarioRunResult, stream: TextIO) -> None:
    expected: ScenarioExpectedCheckExecutionResult
    for expected in result.expected_results:
        if expected.status != FAILED_STATUS:
            continue
        stream.write(
            f"    expected {expected.model_name}: actual={expected.actual_row_count} "
            f"expected={expected.expected_row_count} mismatched={expected.mismatched_row_count}\n"
        )
    assertion: ScenarioAssertionCheckExecutionResult
    for assertion in result.assertion_results:
        if assertion.status != FAILED_STATUS:
            continue
        stream.write(
            f"    assertion {assertion.name}: failing_rows={assertion.failing_row_count}\n"
        )
        if assertion.sample_rows:
            stream.write(f"    sample: {assertion.sample_rows[0]}\n")
