"""Janitor relation retention resolution entrypoint."""

from __future__ import annotations

from sqlbuild.executor.janitor.constants import (
    DIRECT_DEFAULT_RETENTION_DAYS,
)


def resolve_janitor_retention_days(*, override: int | None, configured: int | None) -> int:
    """Resolve CLI override, explicit config, then the mode-specific default."""

    if override is not None:
        return override
    if configured is not None:
        return configured
    return DIRECT_DEFAULT_RETENTION_DAYS
