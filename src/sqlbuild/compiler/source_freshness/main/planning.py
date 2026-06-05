"""Public direct source freshness planning entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.strict.strict_adapter import StrictAdapter
from sqlbuild.compiler.source_freshness.helpers.planning import (
    build_direct_source_freshness_planning_result as _build_direct_source_freshness_planning_result,
)
from sqlbuild.compiler.source_freshness.models import DirectSourceFreshnessPlanningResult
from sqlbuild.spec.models.source import SourceEntry


def build_direct_source_freshness_planning_result(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    state_database: str | None,
    state_schemas: tuple[str, ...],
    observed_at: datetime,
    run_id: str,
    render_qualified_name: Callable[..., str | None],
) -> DirectSourceFreshnessPlanningResult:
    """Observe direct source freshness and compare it to latest append-only state."""

    return _build_direct_source_freshness_planning_result(
        adapter=adapter,
        connection=connection,
        sources=sources,
        state_database=state_database,
        state_schemas=state_schemas,
        observed_at=observed_at,
        run_id=run_id,
        render_qualified_name=render_qualified_name,
    )
