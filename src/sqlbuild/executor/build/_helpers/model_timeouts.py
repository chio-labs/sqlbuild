"""Per-model execution limits: the policy a model attempt runs under and its timeout result."""

from __future__ import annotations

import dataclasses

from sqlbuild._native import ModelPlanEntry
from sqlbuild.executor.run.models import ModelExecutionResult
from sqlbuild.runtime.execution_limits.constants import ITEM_TIMEOUT_CODE
from sqlbuild.runtime.execution_limits.main.timeout_report_lines import timeout_report_lines
from sqlbuild.runtime.execution_limits.models import ItemTimeoutPolicy, ItemTimeoutReport


def model_timeout_policy(entry: ModelPlanEntry) -> ItemTimeoutPolicy | None:
    """The model's `max_duration`, or `None` when it has none or it is disabled."""

    if entry.max_duration is None or entry.max_duration_seconds is None:
        return None
    return ItemTimeoutPolicy(
        limit=entry.max_duration,
        seconds=entry.max_duration_seconds,
        source=entry.max_duration_source or "max_duration",
    )


def timed_out_model_result(
    *, result: ModelExecutionResult, report: ItemTimeoutReport
) -> ModelExecutionResult:
    """The failed attempt reported as a timeout, keeping its phase and failed SQL."""

    lines: list[str] = [
        *timeout_report_lines(report=report, label="Model"),
        "",
        "SQLBuild stopped this attempt and ran no further statements for it; models that",
        "depend on it are skipped as for any failure.",
        "",
        "To allow more time, raise max_duration in the model's MODEL() header, its",
        '[path_defaults] entry or [defaults] in sqlbuild_project.toml, or set it to "disabled".',
    ]
    return dataclasses.replace(
        result,
        error_code=ITEM_TIMEOUT_CODE,
        error_message="\n".join(lines),
        error_help=None,
    )
