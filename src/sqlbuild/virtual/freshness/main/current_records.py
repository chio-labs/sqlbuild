"""Public source freshness current-records entrypoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.spec.models.source import SourceEntry
from sqlbuild.virtual.freshness.helpers.runtime import (
    build_current_virtual_source_freshness_records as _build_current_records,
)
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def build_current_virtual_source_freshness_records(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    virtual_environment_name: str,
    observed_at: datetime,
    previous_records: tuple[SourceFreshnessRecord, ...],
    run_id: str | None = None,
) -> tuple[SourceFreshnessRecord, ...]:
    """Return source records for pre-loader virtual freshness comparisons."""

    return _build_current_records(
        adapter=adapter,
        connection=connection,
        sources=sources,
        virtual_environment_name=virtual_environment_name,
        observed_at=observed_at,
        previous_records=previous_records,
        run_id=run_id,
    )
