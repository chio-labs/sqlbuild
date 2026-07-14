"""Public standard source freshness planning entrypoint."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlbuild.adapter.classes.strict_adapter import StrictAdapter
from sqlbuild.compiler.source_freshness._helpers.planning import (
    build_standard_source_freshness_planning_result as _build_planning_result,
)
from sqlbuild.compiler.source_freshness.models import StandardSourceFreshnessPlanningResult
from sqlbuild.spec.contracts.models import SourceEntry


def build_standard_source_freshness_planning_result(
    *,
    adapter: StrictAdapter,
    connection: Any,
    sources: tuple[SourceEntry, ...],
    state_database: str | None,
    state_schemas: tuple[str, ...],
    observed_at: datetime,
    run_id: str,
    render_qualified_name: Callable[..., str | None],
    state_table_exists_by_schema: dict[str, bool],
) -> StandardSourceFreshnessPlanningResult:
    """Observe standard source freshness and compare it to latest append-only state."""

    return _build_planning_result(
        adapter=adapter,
        connection=connection,
        sources=sources,
        state_database=state_database,
        state_schemas=state_schemas,
        observed_at=observed_at,
        run_id=run_id,
        render_qualified_name=render_qualified_name,
        state_table_exists_by_schema=state_table_exists_by_schema,
    )
