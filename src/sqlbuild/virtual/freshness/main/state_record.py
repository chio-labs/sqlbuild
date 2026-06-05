"""Public source freshness state-record entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.virtual.freshness.helpers.state import (
    source_freshness_record_from_observation as _source_freshness_record_from_observation,
)
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def source_freshness_record_from_observation(
    observation: SourceFreshnessObservation, *, virtual_environment_name: str
) -> SourceFreshnessRecord:
    """Build a persisted state record from an observed source freshness value."""

    return _source_freshness_record_from_observation(
        observation,
        virtual_environment_name=virtual_environment_name,
    )
