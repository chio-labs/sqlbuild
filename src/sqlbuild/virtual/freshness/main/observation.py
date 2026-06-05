"""Public source freshness observation entrypoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.compiler.source_freshness.main.observation import (
    observe_configured_source_freshness as _observe_configured_source_freshness,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.spec.models.source import SourceEntry


def observe_configured_source_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source: SourceEntry,
    observed_at: datetime,
) -> SourceFreshnessObservation:
    """Observe one configured source freshness value."""

    return _observe_configured_source_freshness(
        adapter=adapter,
        connection=connection,
        source=source,
        observed_at=observed_at,
    )
