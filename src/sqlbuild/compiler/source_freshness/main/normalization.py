"""Public shared source freshness normalization entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.source_freshness.helpers.state import (
    normalize_source_freshness_data_version as _normalize_source_freshness_data_version,
)
from sqlbuild.spec.models.types import SourceFreshnessValueKind


def normalize_source_freshness_data_version(
    *, value: object, value_kind: SourceFreshnessValueKind
) -> str:
    """Normalize a source freshness value for stable state storage."""

    return _normalize_source_freshness_data_version(value=value, value_kind=value_kind)
