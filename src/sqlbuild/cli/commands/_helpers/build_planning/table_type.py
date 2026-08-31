"""Table-type downgrade safety enforcement for build commands."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import PlanOutput, TableTypePlanEntry
from sqlbuild.spec.contracts.types import TableTypeDowngradePolicy


def enforce_table_type_downgrade_policy(
    *,
    plan: PlanOutput,
    allow_table_type_downgrade: bool,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Fail or confirm before executing permanent-to-transient conversions."""

    entries: tuple[TableTypePlanEntry, ...] = tuple(
        entry for entry in plan.table_type_entries if entry.downgrade
    )
    denied: tuple[TableTypePlanEntry, ...] = tuple(
        entry for entry in entries if entry.downgrade_policy == TableTypeDowngradePolicy.DENY
    )
    if denied:
        raise CliUserError(
            f"table-type downgrade is denied for {_names(denied)} by table_type_downgrade policy"
        )
    confirmation: tuple[TableTypePlanEntry, ...] = tuple(
        entry
        for entry in entries
        if entry.downgrade_policy == TableTypeDowngradePolicy.REQUIRE_CONFIRMATION
    )
    if not confirmation or allow_table_type_downgrade:
        return
    if not input_stream.isatty():
        raise CliUserError(
            "table-type downgrade requires confirmation",
            help="Pass --allow-table-type-downgrade to confirm in non-interactive runs.",
        )
    expected: str = _confirmation_text(confirmation)
    output_stream.write(
        f"Downgrading {_names(confirmation)} to transient may discard up to 90 days of "
        "time-travel history.\n\n"
    )
    output_stream.write(f"Type `{expected}` to continue: ")
    output_stream.flush()
    if input_stream.readline().strip() != expected:
        raise CliUserError("table-type downgrade cancelled")


def _confirmation_text(entries: tuple[TableTypePlanEntry, ...]) -> str:
    if len(entries) == 1:
        return f"downgrade table type for {entries[0].model_name}"
    return f"downgrade table type for {len(entries)} models"


def _names(entries: tuple[TableTypePlanEntry, ...]) -> str:
    return ", ".join(f"'{entry.model_name}'" for entry in entries)
