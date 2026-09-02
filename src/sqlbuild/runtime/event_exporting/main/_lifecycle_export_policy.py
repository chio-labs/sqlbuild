"""Destination-neutral lifecycle export policy entrypoints."""

from sqlbuild.observability import LifecycleEvent
from sqlbuild.runtime.event_exporting._helpers.policy import (
    lifecycle_export_policy as _lifecycle_export_policy,
)
from sqlbuild.runtime.event_exporting.models import LifecycleExportPolicy


def lifecycle_export_policy(event: LifecycleEvent) -> LifecycleExportPolicy:
    return _lifecycle_export_policy(event)
