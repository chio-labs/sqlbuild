"""dbt interop source freshness state helpers."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_records
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessRecord,
    SourceFreshnessRenderers,
)
from sqlbuild.integrations.dbt.models import DbtInteropPlan


def append_dbt_source_freshness_records(
    *,
    plan: DbtInteropPlan,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    project: CompiledProject,
    on_progress: Callable[[str], None] | None = None,
) -> None:
    """Append observed dbt source freshness records to standard SQLBuild state."""

    if project.effective_target_schema is None:
        return
    if plan.dbt_model_plan is None or plan.dbt_model_plan.source_freshness is None:
        return
    if plan.dbt_model_plan.blocked_unique_ids:
        return
    observed_records: tuple[SourceFreshnessRecord, ...] = (
        plan.dbt_model_plan.source_freshness.observed_records
    )
    if not observed_records:
        return
    freshness_start: float = time.monotonic()
    if on_progress is not None:
        on_progress("Recording dbt source freshness...")
    connection: Any = adapter.connect(connection_config)
    try:
        write_source_freshness_records(
            connection=connection,
            execute=adapter.execute,
            database=project.effective_target_database,
            schema=project.effective_target_schema,
            records=tuple(replace(record, run_id=project.run_id) for record in observed_records),
            renderers=SourceFreshnessRenderers(
                render_qualified_name=adapter.render_qualified_name,
                render_framework_type=adapter.render_framework_type,
                render_insert_records_sql=adapter.render_insert_source_freshness_records_sql,
                render_create_index_sqls=adapter.render_create_source_freshness_index_sqls,
            ),
            transient=adapter.state_tables_transient,
        )
    finally:
        adapter.close(connection)
    if on_progress is not None:
        on_progress(f"Recorded dbt source freshness. ({time.monotonic() - freshness_start:.2f}s)")
