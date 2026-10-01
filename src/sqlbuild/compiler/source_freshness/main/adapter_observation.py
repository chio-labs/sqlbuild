"""Public adapter metadata source freshness batch observation entrypoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.contract.classes.strict_adapter import StrictAdapter
from sqlbuild.compiler.source_freshness._helpers.observation import (
    observe_adapter_sources_freshness as _observe_adapter_sources_freshness,
)
from sqlbuild.compiler.source_freshness.models import AdapterSourceFreshnessBatch
from sqlbuild.spec.contracts.models import SourceEntry


def observe_adapter_sources_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    observed_at: datetime,
) -> AdapterSourceFreshnessBatch:
    """Observe adapter metadata freshness per source, batching the warehouse lookups."""

    return _observe_adapter_sources_freshness(
        adapter=adapter,
        connection=connection,
        sources=sources,
        observed_at=observed_at,
    )
