"""Internal interval algebra for append-only microbatch history."""

from __future__ import annotations

import heapq
from datetime import datetime
from decimal import Decimal

from sqlbuild.compiler.planner.types import CursorType
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
    ProjectedMicrobatchInterval,
    ReplayRequirementProjection,
)
from sqlbuild.microbatches.types import (
    MicrobatchFingerprintStatus,
    MicrobatchRecordType,
    ReplayRequirementState,
)


def project_microbatch_coverage(
    *,
    events: tuple[MicrobatchEvent, ...],
    expected_intervals: tuple[MicrobatchInterval, ...],
    cursor_type: str,
) -> MicrobatchCoverageProjection:
    """Fold completion facts and classify uncovered expected intervals."""

    completions: tuple[MicrobatchEvent, ...] = tuple(
        event
        for event in events
        if event.record_type
        in {
            MicrobatchRecordType.PARTITION_COMPLETION,
            MicrobatchRecordType.SYNTHETIC_COMPLETION,
        }
        and event.partition_start is not None
        and event.partition_end is not None
    )
    boundaries: set[str] = set()
    for event in completions:
        if event.partition_start is not None:
            boundaries.add(event.partition_start)
        if event.partition_end is not None:
            boundaries.add(event.partition_end)
    boundaries.update(interval.start for interval in expected_intervals)
    boundaries.update(interval.end for interval in expected_intervals)
    ordered_boundaries: tuple[str, ...] = tuple(
        sorted(boundaries, key=lambda value: _cursor_value(value=value, cursor_type=cursor_type))
    )
    projected: list[ProjectedMicrobatchInterval] = []
    for start, end, latest in _latest_completion_segments(
        completions=completions,
        ordered_boundaries=ordered_boundaries,
        cursor_type=cursor_type,
    ):
        projected.append(
            ProjectedMicrobatchInterval(
                start=start,
                end=end,
                fingerprint_status=latest.fingerprint_status,
                model_version_hash=latest.model_version_hash,
                record_type=latest.record_type,
                completion_type=latest.completion_type,
                event_id=latest.event_id,
            )
        )

    accounted: list[MicrobatchInterval] = [
        MicrobatchInterval(start=interval.start, end=interval.end) for interval in projected
    ]
    contiguous_frontier: str | None = _minimum_bound(
        values=tuple(interval.start for interval in expected_intervals),
        cursor_type=cursor_type,
    )
    if accounted and contiguous_frontier is not None:
        ordered_accounted: list[MicrobatchInterval] = sorted(
            accounted,
            key=lambda interval: _cursor_value(value=interval.start, cursor_type=cursor_type),
        )
        for interval in ordered_accounted:
            if _lte(left=interval.start, right=contiguous_frontier, cursor_type=cursor_type):
                if _lt(left=contiguous_frontier, right=interval.end, cursor_type=cursor_type):
                    contiguous_frontier = interval.end
            else:
                break

    latest_ordinary_end: str | None = _maximum_bound(
        values=tuple(
            event.partition_end or ""
            for event in completions
            if event.record_type == MicrobatchRecordType.PARTITION_COMPLETION
        ),
        cursor_type=cursor_type,
    )
    known_missing, unaccounted = _classify_uncovered_expected_intervals(
        expected_intervals=expected_intervals,
        accounted=tuple(accounted),
        latest_ordinary_end=latest_ordinary_end,
        cursor_type=cursor_type,
    )

    return MicrobatchCoverageProjection(
        intervals=tuple(projected),
        contiguous_frontier=contiguous_frontier,
        known_missing=tuple(known_missing),
        unaccounted=tuple(unaccounted),
        unknown_fingerprints=tuple(
            MicrobatchInterval(start=interval.start, end=interval.end)
            for interval in projected
            if interval.fingerprint_status == MicrobatchFingerprintStatus.UNKNOWN
        ),
    )


def _latest_completion_segments(
    *,
    completions: tuple[MicrobatchEvent, ...],
    ordered_boundaries: tuple[str, ...],
    cursor_type: str,
) -> tuple[tuple[str, str, MicrobatchEvent], ...]:
    """Sweep interval boundaries while retaining the latest active completion."""

    latest_order: tuple[MicrobatchEvent, ...] = tuple(
        sorted(
            completions,
            key=lambda event: (_created_sort_value(event.created_at), event.event_id),
        )
    )
    latest_rank_by_identity: dict[int, int] = {
        id(event): rank for rank, event in enumerate(latest_order)
    }
    by_start: tuple[MicrobatchEvent, ...] = tuple(
        sorted(
            completions,
            key=lambda event: _cursor_value(
                value=event.partition_start or "", cursor_type=cursor_type
            ),
        )
    )
    active: list[tuple[int, MicrobatchEvent]] = []
    next_event_index: int = 0
    segments: list[tuple[str, str, MicrobatchEvent]] = []
    for boundary_index in range(len(ordered_boundaries) - 1):
        start: str = ordered_boundaries[boundary_index]
        end: str = ordered_boundaries[boundary_index + 1]
        while next_event_index < len(by_start) and _lte(
            left=by_start[next_event_index].partition_start or "",
            right=start,
            cursor_type=cursor_type,
        ):
            event: MicrobatchEvent = by_start[next_event_index]
            heapq.heappush(active, (-latest_rank_by_identity[id(event)], event))
            next_event_index += 1
        while active and not _lte(
            left=end,
            right=active[0][1].partition_end or "",
            cursor_type=cursor_type,
        ):
            heapq.heappop(active)
        if active:
            segments.append((start, end, active[0][1]))
    return tuple(segments)


def _created_sort_value(value: datetime) -> float:
    return value.timestamp()


def _classify_uncovered_expected_intervals(
    *,
    expected_intervals: tuple[MicrobatchInterval, ...],
    accounted: tuple[MicrobatchInterval, ...],
    latest_ordinary_end: str | None,
    cursor_type: str,
) -> tuple[tuple[MicrobatchInterval, ...], tuple[MicrobatchInterval, ...]]:
    """Classify sorted expected intervals without rescanning prior coverage."""

    ordered_expected: tuple[MicrobatchInterval, ...] = tuple(
        sorted(
            expected_intervals,
            key=lambda interval: _cursor_value(value=interval.start, cursor_type=cursor_type),
        )
    )
    ordered_accounted: tuple[MicrobatchInterval, ...] = tuple(
        sorted(
            accounted,
            key=lambda interval: _cursor_value(value=interval.start, cursor_type=cursor_type),
        )
    )
    known_missing: list[MicrobatchInterval] = []
    unaccounted: list[MicrobatchInterval] = []
    accounted_index: int = 0
    for expected in ordered_expected:
        while accounted_index < len(ordered_accounted) and _lte(
            left=ordered_accounted[accounted_index].end,
            right=expected.start,
            cursor_type=cursor_type,
        ):
            accounted_index += 1
        frontier: str = expected.start
        scan_index: int = accounted_index
        gaps: list[MicrobatchInterval] = []
        while scan_index < len(ordered_accounted):
            interval: MicrobatchInterval = ordered_accounted[scan_index]
            if not _lt(left=interval.start, right=expected.end, cursor_type=cursor_type):
                break
            if _lt(left=frontier, right=interval.start, cursor_type=cursor_type):
                gaps.append(MicrobatchInterval(start=frontier, end=interval.start))
            if _lt(left=frontier, right=interval.end, cursor_type=cursor_type):
                frontier = interval.end
            if _lte(left=expected.end, right=frontier, cursor_type=cursor_type):
                break
            scan_index += 1
        if _lt(left=frontier, right=expected.end, cursor_type=cursor_type):
            gaps.append(MicrobatchInterval(start=frontier, end=expected.end))
        for gap in gaps:
            has_accounted_before: bool = accounted_index > 0 or _lt(
                left=expected.start, right=gap.start, cursor_type=cursor_type
            )
            if (
                has_accounted_before
                and latest_ordinary_end is not None
                and _lte(
                    left=gap.end,
                    right=latest_ordinary_end,
                    cursor_type=cursor_type,
                )
            ):
                known_missing.append(gap)
            else:
                unaccounted.append(gap)
    return tuple(known_missing), tuple(unaccounted)


def project_replay_requirement(
    *,
    requirement: MicrobatchEvent,
    current_model_version_hash: str,
    expected_intervals: tuple[MicrobatchInterval, ...],
    coverage: MicrobatchCoverageProjection,
    cursor_type: str,
) -> ReplayRequirementProjection:
    """Derive replay completion without writing mutable requirement status."""

    if requirement.required_model_version_hash != current_model_version_hash:
        return ReplayRequirementProjection(
            requirement=requirement,
            state=ReplayRequirementState.SUPERSEDED,
        )
    missing: list[MicrobatchInterval] = []
    unknown: list[MicrobatchInterval] = []
    for expected in expected_intervals:
        pieces: tuple[ProjectedMicrobatchInterval, ...] = tuple(
            interval
            for interval in coverage.intervals
            if _lt(left=interval.start, right=expected.end, cursor_type=cursor_type)
            and _lt(left=expected.start, right=interval.end, cursor_type=cursor_type)
        )
        if not _is_fully_covered(
            expected=expected,
            accounted=tuple(
                MicrobatchInterval(start=piece.start, end=piece.end) for piece in pieces
            ),
            cursor_type=cursor_type,
        ):
            missing.append(expected)
            continue
        if any(piece.fingerprint_status == MicrobatchFingerprintStatus.UNKNOWN for piece in pieces):
            unknown.append(expected)
            continue
        if any(piece.model_version_hash != current_model_version_hash for piece in pieces):
            missing.append(expected)
    state: ReplayRequirementState
    if missing:
        state = ReplayRequirementState.INCOMPLETE
    elif unknown:
        state = ReplayRequirementState.COMPLETE_WITH_UNKNOWN_FINGERPRINTS
    else:
        state = ReplayRequirementState.VERIFIED_COMPLETE
    return ReplayRequirementProjection(
        requirement=requirement,
        state=state,
        missing=tuple(missing),
        unknown_fingerprints=tuple(unknown),
    )


def latest_active_replay_requirement(
    *, events: tuple[MicrobatchEvent, ...], current_model_version_hash: str
) -> MicrobatchEvent | None:
    """Return only the latest requirement created for the currently compiled version."""

    requirements: tuple[MicrobatchEvent, ...] = tuple(
        event
        for event in events
        if event.record_type == MicrobatchRecordType.REPLAY_REQUIREMENT
        and event.required_model_version_hash == current_model_version_hash
    )
    if not requirements:
        return None
    return max(requirements, key=lambda event: (event.created_at, event.event_id))


def _is_fully_covered(
    *,
    expected: MicrobatchInterval,
    accounted: tuple[MicrobatchInterval, ...] | list[MicrobatchInterval],
    cursor_type: str,
) -> bool:
    frontier: str = expected.start
    for interval in sorted(
        accounted, key=lambda item: _cursor_value(value=item.start, cursor_type=cursor_type)
    ):
        if _lte(left=interval.end, right=frontier, cursor_type=cursor_type):
            continue
        if _lt(left=frontier, right=interval.start, cursor_type=cursor_type):
            return False
        frontier = interval.end
        if _lte(left=expected.end, right=frontier, cursor_type=cursor_type):
            return True
    return False


def _maximum_bound(*, values: tuple[str, ...], cursor_type: str) -> str | None:
    non_empty: tuple[str, ...] = tuple(value for value in values if value)
    return (
        max(non_empty, key=lambda value: _cursor_value(value=value, cursor_type=cursor_type))
        if non_empty
        else None
    )


def _minimum_bound(*, values: tuple[str, ...], cursor_type: str) -> str | None:
    non_empty: tuple[str, ...] = tuple(value for value in values if value)
    return (
        min(non_empty, key=lambda value: _cursor_value(value=value, cursor_type=cursor_type))
        if non_empty
        else None
    )


def _cursor_value(*, value: str, cursor_type: str) -> datetime | Decimal:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(value)
    return Decimal(value)


def _lt(*, left: str, right: str, cursor_type: str) -> bool:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(left) < datetime.fromisoformat(right)
    return Decimal(left) < Decimal(right)


def _lte(*, left: str, right: str, cursor_type: str) -> bool:
    if cursor_type == CursorType.TIMESTAMP:
        return datetime.fromisoformat(left) <= datetime.fromisoformat(right)
    return Decimal(left) <= Decimal(right)
