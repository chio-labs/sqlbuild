"""Time-travel retention decrease safety enforcement for build commands."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import PlanOutput, RetentionPlanEntry
from sqlbuild.spec.contracts.types import RetentionDecreasePolicy


def enforce_retention_decrease_policy(
    *,
    plan: PlanOutput,
    allow_retention_decrease: bool,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Fail or confirm before lowering live time-travel retention."""

    entries: tuple[RetentionPlanEntry, ...] = tuple(
        entry for entry in plan.retention_entries if entry.decreases
    )
    denied: tuple[RetentionPlanEntry, ...] = tuple(
        entry for entry in entries if entry.decrease_policy == RetentionDecreasePolicy.DENY
    )
    if denied:
        raise CliUserError(
            f"time travel retention decrease is denied for {_names(denied)}",
            help=(
                "Keep the current retention, or set the target's "
                "time_travel_retention_decrease to 'require_confirmation' or 'allow'."
            ),
        )
    confirmation: tuple[RetentionPlanEntry, ...] = tuple(
        entry
        for entry in entries
        if entry.decrease_policy == RetentionDecreasePolicy.REQUIRE_CONFIRMATION
    )
    if not confirmation or allow_retention_decrease:
        return
    if not input_stream.isatty():
        raise CliUserError(
            "time travel retention decrease requires confirmation",
            help="Pass --allow-retention-decrease to confirm in non-interactive runs.",
        )
    expected: str = _confirmation_text(confirmation)
    output_stream.write(
        f"Decreasing time travel retention for {_names(confirmation)} permanently discards "
        "history older than the new retention.\n\n"
    )
    output_stream.write(f"Type `{expected}` to continue: ")
    output_stream.flush()
    if input_stream.readline().strip() != expected:
        raise CliUserError("time travel retention decrease cancelled")


def _model_names(entries: tuple[RetentionPlanEntry, ...]) -> tuple[str, ...]:
    names: dict[str, None] = {}
    for entry in entries:
        names.update(dict.fromkeys(entry.model_names))
    return tuple(names)


def _confirmation_text(entries: tuple[RetentionPlanEntry, ...]) -> str:
    names: tuple[str, ...] = _model_names(entries)
    if len(names) == 1:
        return f"decrease retention for {names[0]}"
    return f"decrease retention for {len(names)} models"


def _names(entries: tuple[RetentionPlanEntry, ...]) -> str:
    return ", ".join(f"'{name}'" for name in _model_names(entries))
