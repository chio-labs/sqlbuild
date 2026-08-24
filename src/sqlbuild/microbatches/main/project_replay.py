"""Public replay-requirement projection entrypoint."""

from sqlbuild.microbatches._helpers.projection import (
    project_replay_requirement as _project_replay_requirement,
)
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
    ReplayRequirementProjection,
)


def project_replay_requirement(
    *,
    requirement: MicrobatchEvent,
    current_model_version_hash: str,
    expected_intervals: tuple[MicrobatchInterval, ...],
    coverage: MicrobatchCoverageProjection,
    cursor_type: str,
) -> ReplayRequirementProjection:
    """Project derived completion state for one replay requirement."""

    return _project_replay_requirement(
        requirement=requirement,
        current_model_version_hash=current_model_version_hash,
        expected_intervals=expected_intervals,
        coverage=coverage,
        cursor_type=cursor_type,
    )
