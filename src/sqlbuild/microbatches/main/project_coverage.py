"""Public physical-coverage projection entrypoint."""

from sqlbuild.microbatches._helpers.projection import (
    project_microbatch_coverage as _project_microbatch_coverage,
)
from sqlbuild.microbatches.models import (
    MicrobatchCoverageProjection,
    MicrobatchEvent,
    MicrobatchInterval,
)


def project_microbatch_coverage(
    *,
    events: tuple[MicrobatchEvent, ...],
    expected_intervals: tuple[MicrobatchInterval, ...],
    cursor_type: str,
) -> MicrobatchCoverageProjection:
    """Project physical and fingerprint coverage for expected intervals."""

    return _project_microbatch_coverage(
        events=events,
        expected_intervals=expected_intervals,
        cursor_type=cursor_type,
    )
