"""Public source freshness runtime observation entrypoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.spec.contracts.models import SourceEntry
from sqlbuild.virtual.freshness._helpers.runtime import (
    observe_virtual_environment_source_freshness as _observe_virtual_environment_source_freshness,
)
from sqlbuild.virtual.freshness.models import SourceFreshnessRuntimeResult
from sqlbuild.virtual.state.models import SourceFreshnessRecord


def observe_virtual_environment_source_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    virtual_environment_name: str,
    observed_at: datetime,
    run_id: str | None = None,
    load_results: tuple[Any, ...] = (),
    previous_records: tuple[SourceFreshnessRecord, ...] = (),
) -> SourceFreshnessRuntimeResult:
    """Observe current source freshness records without using them for skip decisions."""

    return _observe_virtual_environment_source_freshness(
        adapter=adapter,
        connection=connection,
        sources=sources,
        virtual_environment_name=virtual_environment_name,
        observed_at=observed_at,
        run_id=run_id,
        load_results=load_results,
        previous_records=previous_records,
    )
