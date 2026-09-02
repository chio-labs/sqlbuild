"""Lifecycle export severity comparison entrypoint."""

from sqlbuild.runtime.event_exporting._helpers.policy import (
    severity_at_least as _severity_at_least,
)


def severity_at_least(*, severity: str, minimum: str) -> bool:
    return _severity_at_least(severity=severity, minimum=minimum)
