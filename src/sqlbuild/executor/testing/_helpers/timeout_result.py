"""The result of a SQL unit test that ran out of time."""

from __future__ import annotations

from sqlbuild._native import SqlTestPlanEntry
from sqlbuild.executor.testing.constants import (
    INLINED_MODEL_DISPLAY_LIMIT,
    MINUTE_SUGGESTION_THRESHOLD_SECONDS,
    SECONDS_PER_MINUTE,
    SQL_TEST_TIMEOUT_CODE,
)
from sqlbuild.executor.testing.models import SqlTestExecutionResult, StepResult
from sqlbuild.executor.testing.types import SqlTestOutcome
from sqlbuild.runtime.execution_limits.main.timeout_report_lines import timeout_report_lines
from sqlbuild.runtime.execution_limits.models import ItemTimeoutReport

_SCENARIO_ADVICE: tuple[str, ...] = (
    "  2. If this test checks behaviour across several models, consider a scenario",
    "     (tests/scenarios/). A unit test inlines every real model into one statement,",
    "     so the warehouse compiles and optimises the whole chain at once; a scenario",
    "     builds each model step by step, compiling each statement separately.",
)


def timed_out_result(
    *, test_entry: SqlTestPlanEntry, report: ItemTimeoutReport
) -> SqlTestExecutionResult:
    """A TIMEOUT result naming the limit, its source, the cancellation and how to proceed."""

    message: str = timeout_message(test_entry=test_entry, report=report)
    model_name: str = next(
        (step.model_name for step in test_entry.chain if step.expected_cte_sql is not None),
        test_entry.name,
    )
    return SqlTestExecutionResult(
        test_name=test_entry.name,
        outcome=SqlTestOutcome.TIMEOUT,
        source_path=test_entry.source_path,
        block_index=test_entry.block_index,
        parent_name=test_entry.parent_name,
        case_name=test_entry.case_name,
        case_index=test_entry.case_index,
        case_fingerprint=test_entry.case_fingerprint,
        parameter_schema=test_entry.parameter_schema,
        parameter_values=test_entry.parameter_values,
        step_results=(
            StepResult(
                model_name=model_name,
                outcome=SqlTestOutcome.TIMEOUT,
                error_code=SQL_TEST_TIMEOUT_CODE,
                error_message=message,
            ),
        ),
        error_code=SQL_TEST_TIMEOUT_CODE,
        error_message=message,
        real_model_count=test_entry.real_model_count,
        timeout=report,
    )


def timeout_message(*, test_entry: SqlTestPlanEntry, report: ItemTimeoutReport) -> str:
    """Key facts first, then the options in order: mock, consider a scenario, raise the limit."""

    lines: list[str] = [
        *timeout_report_lines(report=report, label="SQL unit test"),
    ]
    inlined: list[str] = [
        step.model_name for step in test_entry.chain if step.expected_cte_sql is None
    ]
    raised: str = _raised_limit(report)
    raise_lines: list[str] = [
        f'set TEST(timeout "{raised}") on this test, [settings] test_timeout = "{raised}"',
        "in sqlbuild_project.toml (or sqlbuild_local.toml), or --test-timeout for one run.",
    ]
    if test_entry.real_model_count is None or not inlined:
        lines.extend(["", f"To allow more time, {raise_lines[0]}", raise_lines[1]])
        return "\n".join(lines)
    shown: list[str] = inlined[-INLINED_MODEL_DISPLAY_LIMIT:]
    more: str = f" and {len(inlined) - len(shown)} more" if len(inlined) > len(shown) else ""
    lines.extend(
        [
            "",
            f"This test inlines {len(inlined)} real "
            f"{'model' if len(inlined) == 1 else 'models'} beyond the model under test into one "
            "statement:",
            f"  {', '.join(shown)}{more}",
            "",
            "Options:",
            "  1. Mock the inlined models closest to the model under test to cut the chain,",
            f"     for example __ref__{shown[-1]} AS (SELECT ...).",
            *_SCENARIO_ADVICE,
            f"  3. To allow more time, {raise_lines[0]}",
            f"     {raise_lines[1]}",
        ]
    )
    return "\n".join(lines)


def _raised_limit(report: ItemTimeoutReport) -> str:
    seconds: float = max(report.elapsed_seconds * 2, 1.0)
    if seconds >= MINUTE_SUGGESTION_THRESHOLD_SECONDS:
        return f"{int(seconds // SECONDS_PER_MINUTE) + 1}m"
    return f"{int(seconds) + 1}s"
