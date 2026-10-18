"""Per-scenario time limits and the result of a scenario that ran out of time."""

from __future__ import annotations

import dataclasses

from sqlbuild._native import CompiledSqlScenario, execution_limit_seconds
from sqlbuild.executor.scenario.models import ScenarioRunResult
from sqlbuild.executor.scheduling.types import ExecutionStatus
from sqlbuild.runtime.execution_limits.constants import ITEM_TIMEOUT_CODE
from sqlbuild.runtime.execution_limits.main.timeout_report_lines import timeout_report_lines
from sqlbuild.runtime.execution_limits.models import (
    ItemTimeoutPolicy,
    ItemTimeoutReport,
    RunItemTimeouts,
)

_TIMEOUT_KEY: str = "timeout"


def scenario_timeout(
    *, scenario: CompiledSqlScenario, timeouts: RunItemTimeouts | None
) -> ItemTimeoutPolicy | None:
    """The CLI limit, else the SCENARIO() timeout, else the target's or project's."""

    declared: object = scenario.scenario_file.header_values.get(_TIMEOUT_KEY)
    text: str | None = declared if isinstance(declared, str) else None
    location: str = scenario.source_path.as_posix() if scenario.source_path else scenario.name
    return (timeouts or RunItemTimeouts()).resolve(
        declared=text,
        declared_seconds=None if text is None else execution_limit_seconds(text),
        declared_source=f"SCENARIO() timeout in {location}",
    )


def timed_out_scenario_result(
    *, result: ScenarioRunResult, report: ItemTimeoutReport
) -> ScenarioRunResult:
    """The scenario reported as timed out, keeping the step results it reached."""

    lines: list[str] = [
        *timeout_report_lines(report=report, label="Scenario"),
        "",
        'To allow more time, set SCENARIO(timeout "...") in the scenario file,',
        "[settings] scenario_timeout in sqlbuild_project.toml (or sqlbuild_local.toml), or",
        "--scenario-timeout for one run.",
    ]
    return dataclasses.replace(
        result,
        status=ExecutionStatus.FAILED,
        error_code=ITEM_TIMEOUT_CODE,
        error_help=None,
        error_message="\n".join(lines),
    )
