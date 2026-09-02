"""Lifecycle export policy catalog entrypoint."""

from collections.abc import Mapping

from sqlbuild.runtime.event_exporting._helpers.policy import (
    lifecycle_export_policy_catalog as _lifecycle_export_policy_catalog,
)
from sqlbuild.runtime.event_exporting.models import LifecycleExportPolicy


def lifecycle_export_policy_catalog() -> Mapping[str, LifecycleExportPolicy]:
    return _lifecycle_export_policy_catalog()
