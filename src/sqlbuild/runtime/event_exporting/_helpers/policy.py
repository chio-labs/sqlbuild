"""Authoritative destination-neutral lifecycle export policy."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting.constants import (
    EVENT_EXPORT_SEVERITY_RANKS,
    LIFECYCLE_EXPORT_DIMENSIONS,
)
from sqlbuild.runtime.event_exporting.models import LifecycleExportPolicy

_LIFECYCLE_EXPORT_POLICY: Mapping[str, LifecycleExportPolicy] = MappingProxyType(
    {
        event_type: LifecycleExportPolicy(*dimensions)
        for event_type, dimensions in LIFECYCLE_EXPORT_DIMENSIONS.items()
    }
)


def lifecycle_export_policy(event: LifecycleEvent) -> LifecycleExportPolicy:
    """Return destination-neutral dimensions for an already validated event."""

    return _LIFECYCLE_EXPORT_POLICY[event.event_type]


def lifecycle_export_policy_catalog() -> Mapping[str, LifecycleExportPolicy]:
    """Return the immutable policy catalog for validation and documentation tests."""

    return _LIFECYCLE_EXPORT_POLICY


def severity_at_least(*, severity: str, minimum: str) -> bool:
    """Return whether a catalogued severity meets a configured minimum."""

    return EVENT_EXPORT_SEVERITY_RANKS[severity] >= EVENT_EXPORT_SEVERITY_RANKS[minimum]


def stricter_severity(*, first: str, second: str | None) -> str:
    """Return the stricter of a required and optional minimum severity."""

    if second is None or EVENT_EXPORT_SEVERITY_RANKS[first] >= EVENT_EXPORT_SEVERITY_RANKS[second]:
        return first
    return second
