"""Lifecycle export severity narrowing entrypoint."""

from sqlbuild.runtime.event_exporting._helpers.policy import (
    stricter_severity as _stricter_severity,
)
from sqlbuild.spec.contracts.types import EventExportSeverity


def stricter_severity(
    *,
    first: str | EventExportSeverity,
    second: str | EventExportSeverity | None,
) -> EventExportSeverity:
    """Select a stricter severity while preserving string-accepting callers."""

    return _stricter_severity(
        first=EventExportSeverity(first),
        second=EventExportSeverity(second) if second is not None else None,
    )
