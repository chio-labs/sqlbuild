"""Public shared source freshness observation entrypoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlbuild.adapter.classes.strict_adapter import StrictAdapter
from sqlbuild.compiler.source_freshness._helpers.observation import (
    observe_configured_source_freshness as _observe_configured_source_freshness,
)
from sqlbuild.compiler.source_freshness.models import SourceFreshnessObservation
from sqlbuild.spec.contracts.models import SourceEntry


def observe_configured_source_freshness(
    *,
    adapter: StrictAdapter,
    connection: Any,
    source: SourceEntry,
    observed_at: datetime,
) -> SourceFreshnessObservation:
    """Observe one source freshness config and return a comparable data version."""

    return _observe_configured_source_freshness(
        adapter=adapter,
        connection=connection,
        source=source,
        observed_at=observed_at,
    )
