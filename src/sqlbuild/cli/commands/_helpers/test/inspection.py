"""Resolved SQL-test plan inspection output."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TextIO

from sqlbuild.compiler.planner.models import PlanOutput, PlanWarning, SqlTestPlanEntry
from sqlbuild.compiler.planner.types import WarningSeverity


def write_test_plan_inspection(*, stream: TextIO, plan_output: PlanOutput) -> int:
    """Write selected test fixture boundaries and real model chains without executing them."""

    stream.write("\nResolved test plan\n\n")
    for entry in plan_output.test_entries:
        stream.write(f"{_entry_label(entry)}\n")
        _write_names(stream=stream, label="mocked sources", names=entry.mock_source_names)
        _write_names(stream=stream, label="mocked refs", names=entry.mock_ref_names)
        _write_names(stream=stream, label="mocked seeds", names=entry.mock_seed_names)
        _write_names(stream=stream, label="mocked dbt refs", names=entry.mock_dbt_ref_names)
        _write_names(
            stream=stream,
            label="real models",
            names=tuple(step.model_name for step in entry.chain),
        )
        _write_names(
            stream=stream,
            label="expected models",
            names=tuple(
                step.model_name for step in entry.chain if step.expected_cte_sql is not None
            ),
        )
        for mock_name in entry.mock_ref_names:
            stream.write(f"  boundary: {mock_name} is replaced by __ref__{mock_name}\n")
        stream.write("\n")
    error_warnings: tuple[PlanWarning, ...] = tuple(
        warning for warning in plan_output.warnings if warning.severity == WarningSeverity.ERROR
    )
    for warning in plan_output.warnings:
        stream.write(f"  {warning.severity.value}: {warning.message}\n")
    outcome: str = "failed" if error_warnings else "complete"
    stream.write(
        f"Test plan inspection {outcome}: {len(plan_output.test_entries)} selected, "
        f"{len(error_warnings)} errors.\n"
    )
    stream.flush()
    return 1 if error_warnings else 0


def _write_names(*, stream: TextIO, label: str, names: Iterable[str]) -> None:
    values: tuple[str, ...] = tuple(names)
    stream.write(f"  {label}: {', '.join(values) if values else 'none'}\n")


def _entry_label(entry: SqlTestPlanEntry) -> str:
    if entry.case_name is None:
        return entry.name
    return f"{entry.parent_name or entry.name} [{entry.case_name}]"
