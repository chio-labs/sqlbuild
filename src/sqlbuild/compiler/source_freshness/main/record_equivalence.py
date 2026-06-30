"""Public source freshness record equivalence entrypoint."""

from __future__ import annotations

from sqlbuild.compiler.source_freshness.helpers.state import (
    source_freshness_records_equivalent as _source_freshness_records_equivalent,
)
from sqlbuild.compiler.source_freshness.types import SourceFreshnessComparableRecord


def source_freshness_records_equivalent(
    *,
    previous_record: SourceFreshnessComparableRecord,
    current_record: SourceFreshnessComparableRecord,
    lag_tolerance: str | None = None,
) -> bool:
    """Return whether two source freshness records are equivalent for skip decisions."""

    return _source_freshness_records_equivalent(
        previous_record=previous_record,
        current_record=current_record,
        lag_tolerance=lag_tolerance,
    )
