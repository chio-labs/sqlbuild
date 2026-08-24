"""Derive physical-version retention roots from virtual microbatch replay history."""

from __future__ import annotations

from sqlbuild.microbatches.main.project_coverage import project_microbatch_coverage
from sqlbuild.microbatches.main.project_replay import project_replay_requirement
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
    ReplayRequirementProjection,
)
from sqlbuild.microbatches.types import MicrobatchRecordType, ReplayRequirementState
from sqlbuild.virtual.state.models import MicrobatchReplayRoot


def active_microbatch_replay_roots(
    *, events: tuple[MicrobatchEvent, ...]
) -> tuple[MicrobatchReplayRoot, ...]:
    """Return model versions whose latest replay requirement is incomplete."""

    latest_requirements: dict[tuple[str, str], MicrobatchEvent] = {}
    for event in events:
        if (
            event.record_type != MicrobatchRecordType.REPLAY_REQUIREMENT
            or event.required_model_version_hash is None
        ):
            continue
        identity: tuple[str, str] = (
            event.scope.model_name,
            event.scope.physical_generation_id.partition(":")[0],
        )
        current: MicrobatchEvent | None = latest_requirements.get(identity)
        if current is None or (current.created_at, current.event_id) < (
            event.created_at,
            event.event_id,
        ):
            latest_requirements[identity] = event

    roots: list[MicrobatchReplayRoot] = []
    for requirement in latest_requirements.values():
        required_version_hash: str | None = requirement.required_model_version_hash
        if required_version_hash is None:
            continue
        scope_events: tuple[MicrobatchEvent, ...] = tuple(
            event
            for event in events
            if event.scope.scope_kind == requirement.scope.scope_kind
            and event.scope.scope_key == requirement.scope.scope_key
            and event.scope.physical_generation_id == requirement.scope.physical_generation_id
        )
        expected: tuple[MicrobatchInterval, ...] = (
            MicrobatchInterval(start=requirement.run_start, end=requirement.run_end),
        )
        coverage: MicrobatchCoverageProjection = project_microbatch_coverage(
            events=scope_events,
            expected_intervals=expected,
            cursor_type=requirement.cursor_type,
        )
        projection: ReplayRequirementProjection = project_replay_requirement(
            requirement=requirement,
            current_model_version_hash=required_version_hash,
            expected_intervals=expected,
            coverage=coverage,
            cursor_type=requirement.cursor_type,
        )
        if projection.state == ReplayRequirementState.INCOMPLETE:
            roots.append(
                MicrobatchReplayRoot(
                    model_name=requirement.scope.model_name,
                    version_hash=required_version_hash,
                    previous_version_hash=requirement.previous_model_version_hash,
                )
            )
    return tuple(sorted(roots, key=lambda root: (root.model_name, root.version_hash)))
