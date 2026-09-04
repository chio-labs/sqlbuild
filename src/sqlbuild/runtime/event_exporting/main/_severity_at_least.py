"""Lifecycle export severity comparison entrypoint."""

from sqlbuild.runtime.event_exporting._helpers.policy import (
    severity_at_least as _severity_at_least,
)
from sqlbuild.spec.contracts.types import EventExportSeverity


def severity_at_least(
    *, severity: str | EventExportSeverity, minimum: str | EventExportSeverity
) -> bool:
    """Compare severities while preserving the public string-accepting API."""

    return _severity_at_least(
        severity=EventExportSeverity(severity), minimum=EventExportSeverity(minimum)
    )
