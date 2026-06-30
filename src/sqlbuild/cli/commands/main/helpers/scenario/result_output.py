"""Scenario result row rendering shared across warehouse, local, and snapshot paths."""

from __future__ import annotations

from pathlib import Path
from typing import TextIO

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.cli.commands.main.helpers.scenario.constants import FAILED_STATUS, SUCCESS_STATUS
from sqlbuild.cli.commands.main.shared.helpers.targets.scenario_runtime import (
    write_local_scenario_runtime_target,
    write_scenario_runtime_target,
)
from sqlbuild.compiler.planner.models import ScenarioArtifactName, ScenarioExecutionPlan
from sqlbuild.compiler.planner.types import ScenarioArtifactKind
from sqlbuild.executor.scenario.models import (
    ScenarioAssertionExpectationExecutionResult,
    ScenarioExpectedExpectationExecutionResult,
    ScenarioRunResult,
)
from sqlbuild.shared.classes.transient_status_reporter import TransientStatusReporter
from sqlbuild.shared.helpers.output.cli_style import CliStyle
from sqlbuild.shared.main.coded_error_text import format_coded_error

_SCENARIO_NAME_WIDTH: int = 64
_EXPECTATION_LABEL_WIDTH: int = 10
_EXPECTATION_NAME_WIDTH: int = 50


def complete_scenario_run(
    *,
    scenario_status: TransientStatusReporter,
    status_is_tty: bool,
    target_dir: Path,
    adapter: BaseAdapter,
    scenario_plan: ScenarioExecutionPlan | None,
    result: ScenarioRunResult,
    progress_stream: TextIO,
    use_color: bool,
) -> None:
    """Render one completed scenario row and persist its runtime target."""

    if status_is_tty:
        scenario_status.close()
    if scenario_plan is not None and result.local_status is None:
        write_scenario_runtime_target(
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
        )
    if scenario_plan is not None and result.local_status is not None:
        write_local_scenario_runtime_target(
            target_dir=target_dir,
            adapter=adapter,
            scenario_plan=scenario_plan,
            result=result,
        )
    write_scenario_result(result=result, stream=progress_stream, use_color=use_color)


def write_scenario_result(*, result: ScenarioRunResult, stream: TextIO, use_color: bool) -> None:
    """Render one scenario result with expectations and retained artifacts."""

    status_text: str = (
        result.local_status.value
        if result.local_status is not None
        else "PASS"
        if result.status == SUCCESS_STATUS
        else "FAIL"
    )
    style: CliStyle = CliStyle(use_color=use_color)
    status: str = style.status(status_text)
    stream.write(f"{result.scenario_name:<{_SCENARIO_NAME_WIDTH}} {status}\n")
    if result.error_message:
        rendered_error_message: str = render_result_error(
            error_code=result.error_code,
            error_message=result.error_message,
            error_help=result.error_help,
            use_color=use_color,
        )
        error_line: str
        for error_line in rendered_error_message.splitlines():
            stream.write(f"    {error_line}\n")
        if not result.retained and result.local_status is None:
            stream.write("    Rerun with --retain to inspect scenario-owned artifacts.\n")
    _write_expectations(result=result, stream=stream, use_color=use_color)
    if result.retained and result.relation_map is not None:
        stream.write("    Retained relations:\n")
        artifact: ScenarioArtifactName
        for artifact in result.relation_map.artifacts:
            kind: str = ScenarioArtifactKind(artifact.identity.kind).value
            stream.write(
                f"      {kind:<6} {artifact.identity.logical_name} -> {artifact.physical_name}\n"
            )
    if result.retained and result.local_duckdb_path is not None:
        stream.write(f"    Retained local DuckDB: {result.local_duckdb_path.as_posix()}\n")
    _write_expectation_failures(result=result, stream=stream)
    stream.flush()


def render_result_error(
    *,
    error_code: str | None,
    error_message: str,
    error_help: str | None = None,
    use_color: bool = False,
) -> str:
    """Render a scenario result error with optional code and help."""

    if error_code is None:
        return error_message
    return format_coded_error(
        code=error_code,
        message=error_message,
        help=error_help,
        use_color=use_color,
    )


def _write_expectations(*, result: ScenarioRunResult, stream: TextIO, use_color: bool) -> None:
    style: CliStyle = CliStyle(use_color=use_color)
    expected: ScenarioExpectedExpectationExecutionResult
    for expected in result.expected_results:
        status_text: str = "FAIL" if expected.status == FAILED_STATUS else "PASS"
        status: str = style.status(status_text)
        detail: str = ""
        if expected.status == FAILED_STATUS:
            detail = f"  {expected.mismatched_row_count} mismatched"
        item_name: str = f"expected {expected.model_name}"
        stream.write(
            f"    {'expect':<{_EXPECTATION_LABEL_WIDTH}}"
            f"{item_name:<{_EXPECTATION_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )
        if expected.error_message is not None:
            rendered_error: str = render_result_error(
                error_code=expected.error_code,
                error_message=expected.error_message,
                error_help=expected.error_help,
                use_color=use_color,
            )
            stream.write(f"{'':>14}{rendered_error}\n")
    assertion: ScenarioAssertionExpectationExecutionResult
    for assertion in result.assertion_results:
        status_text = "FAIL" if assertion.status == FAILED_STATUS else "PASS"
        status = style.status(status_text)
        row_label: str = "row" if assertion.failing_row_count == 1 else "rows"
        detail = ""
        if assertion.status == FAILED_STATUS:
            detail = f"  {assertion.failing_row_count} {row_label}"
        item_name = f"assertion {assertion.name}"
        stream.write(
            f"    {'expect':<{_EXPECTATION_LABEL_WIDTH}}"
            f"{item_name:<{_EXPECTATION_NAME_WIDTH}} "
            f"{status}{detail}\n"
        )
        if assertion.error_message is not None:
            rendered_error = render_result_error(
                error_code=assertion.error_code,
                error_message=assertion.error_message,
                error_help=assertion.error_help,
                use_color=use_color,
            )
            stream.write(f"{'':>14}{rendered_error}\n")


def _write_expectation_failures(*, result: ScenarioRunResult, stream: TextIO) -> None:
    expected: ScenarioExpectedExpectationExecutionResult
    for expected in result.expected_results:
        if expected.status != FAILED_STATUS:
            continue
        stream.write(
            f"    expected {expected.model_name}: actual={expected.actual_row_count} "
            f"expected={expected.expected_row_count} mismatched={expected.mismatched_row_count}\n"
        )
    assertion: ScenarioAssertionExpectationExecutionResult
    for assertion in result.assertion_results:
        if assertion.status != FAILED_STATUS:
            continue
        stream.write(
            f"    assertion {assertion.name}: failing_rows={assertion.failing_row_count}\n"
        )
        if assertion.sample_rows:
            stream.write(f"    sample: {assertion.sample_rows[0]}\n")
