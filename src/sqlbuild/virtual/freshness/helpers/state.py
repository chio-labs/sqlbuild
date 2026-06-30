"""Virtual source freshness state-record helpers."""

from __future__ import annotations

from sqlbuild.compiler.source_freshness.main.operations.data_version_hash import (
    source_freshness_data_version_hash,
)
from sqlbuild.compiler.source_freshness.main.operations.normalization import (
    normalize_source_freshness_data_version,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def source_freshness_record_from_observation(
    observation: SourceFreshnessObservation, *, virtual_environment_name: str
) -> SourceFreshnessRecord:
    """Build a persisted virtual state record from an observed source freshness value."""

    normalized_data_version: str = normalize_source_freshness_data_version(
        value=observation.data_version,
        value_kind=observation.value_kind,
    )
    return SourceFreshnessRecord(
        virtual_environment_name=virtual_environment_name,
        source_name=observation.source_name,
        strategy=observation.strategy.value,
        value_kind=observation.value_kind.value,
        data_version=normalized_data_version,
        data_version_hash=source_freshness_data_version_hash(
            source_name=observation.source_name,
            strategy=observation.strategy,
            value_kind=observation.value_kind,
            data_version=normalized_data_version,
        ),
        observed_at=observation.observed_at,
    )
