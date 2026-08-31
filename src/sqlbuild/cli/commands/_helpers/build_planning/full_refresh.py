"""Full-refresh safety enforcement for build commands."""

from __future__ import annotations

from typing import TextIO

from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import (
    MaterializationType,
    PlanReason,
    SnapshotFullRefreshPolicy,
)
from sqlbuild.spec.contracts.models import SnapshotsConfig

_POLICY_STRICTNESS: dict[SnapshotFullRefreshPolicy, int] = {
    SnapshotFullRefreshPolicy.ALLOW: 0,
    SnapshotFullRefreshPolicy.REQUIRE_CONFIRMATION: 1,
    SnapshotFullRefreshPolicy.DENY: 2,
}


def enforce_snapshot_full_refresh_policy(
    *,
    plan: PlanOutput,
    snapshots_config: SnapshotsConfig,
    allow_snapshot_full_refresh: bool,
    input_stream: TextIO,
    output_stream: TextIO,
) -> None:
    """Fail or confirm before executing protected full-refresh entries."""

    snapshot_entries: tuple[ModelPlanEntry, ...] = tuple(
        entry
        for entry in plan.model_entries
        if entry.materialization_type == MaterializationType.SNAPSHOT
        and entry.reason == PlanReason.FULL_REFRESH
    )
    if not snapshot_entries:
        return

    denied: tuple[ModelPlanEntry, ...] = tuple(
        entry
        for entry in snapshot_entries
        if _effective_policy(entry=entry, snapshots_config=snapshots_config)
        == SnapshotFullRefreshPolicy.DENY
    )
    if denied:
        names: str = _model_names(denied)
        raise CliUserError(
            f"full refresh is denied for snapshot model {names} by snapshot_full_refresh policy",
            code="C238",
            help=(
                "Set a less strict project/model snapshot_full_refresh policy only if "
                "the snapshot history is recoverable."
            ),
        )

    confirmation_required: tuple[ModelPlanEntry, ...] = tuple(
        entry
        for entry in snapshot_entries
        if _effective_policy(entry=entry, snapshots_config=snapshots_config)
        == SnapshotFullRefreshPolicy.REQUIRE_CONFIRMATION
    )
    if not confirmation_required or allow_snapshot_full_refresh:
        return

    if not input_stream.isatty():
        raise CliUserError(
            "snapshot full refresh requires confirmation",
            code="C239",
            help="Pass --allow-snapshot-full-refresh to confirm in non-interactive runs.",
        )

    if not _confirm(
        entries=confirmation_required, input_stream=input_stream, output_stream=output_stream
    ):
        raise CliUserError("snapshot full refresh cancelled", code="C240")


def _effective_policy(
    *, entry: ModelPlanEntry, snapshots_config: SnapshotsConfig
) -> SnapshotFullRefreshPolicy:
    project_policy: SnapshotFullRefreshPolicy = SnapshotFullRefreshPolicy(
        snapshots_config.historical_full_refresh
        if entry.observed_at_column is not None
        else snapshots_config.current_state_full_refresh
    )
    if entry.snapshot_full_refresh is None:
        return project_policy
    model_policy: SnapshotFullRefreshPolicy = SnapshotFullRefreshPolicy(entry.snapshot_full_refresh)
    return max((project_policy, model_policy), key=lambda policy: _POLICY_STRICTNESS[policy])


def _confirm(
    *, entries: tuple[ModelPlanEntry, ...], input_stream: TextIO, output_stream: TextIO
) -> bool:
    expected: str = _confirmation_text(entries)
    names: str = _model_names(entries)
    output_stream.write(
        f"Full refresh of snapshot model {names} may permanently discard unrecoverable history.\n\n"
    )
    output_stream.write(f"Type `{expected}` to continue: ")
    output_stream.flush()
    response: str = input_stream.readline().strip()
    return response == expected


def _confirmation_text(entries: tuple[ModelPlanEntry, ...]) -> str:
    if len(entries) == 1:
        return f"discard snapshot history for {entries[0].name}"
    return f"discard snapshot history for {len(entries)} models"


def _model_names(entries: tuple[ModelPlanEntry, ...]) -> str:
    if len(entries) == 1:
        return f"'{entries[0].name}'"
    return ", ".join(f"'{entry.name}'" for entry in entries)
