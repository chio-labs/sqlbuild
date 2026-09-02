"""Lifecycle export severity narrowing entrypoint."""

from sqlbuild.runtime.event_exporting._helpers.policy import (
    stricter_severity as _stricter_severity,
)


def stricter_severity(*, first: str, second: str | None) -> str:
    return _stricter_severity(first=first, second=second)
