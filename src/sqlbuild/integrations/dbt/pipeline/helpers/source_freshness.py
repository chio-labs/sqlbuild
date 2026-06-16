"""dbt interop source freshness state helpers."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject
from sqlbuild.compiler.source_freshness.main.write import write_source_freshness_record
from sqlbuild.compiler.source_freshness.models import SourceFreshnessRecord
from sqlbuild.integrations.dbt.models import DbtInteropPlan


def append_dbt_source_freshness_records(
    *,
    plan: DbtInteropPlan,
    adapter: BaseAdapter,
    connection_config: dict[str, object],
    project: CompiledProject,
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
    connection: Any = adapter.connect(connection_config)
    try:
        record: SourceFreshnessRecord
        for record in observed_records:
            write_source_freshness_record(
                connection=connection,
                execute=adapter.execute,
                database=project.effective_target_database,
                schema=project.effective_target_schema,
                record=replace(record, run_id=project.run_id),
                render_qualified_name=adapter.render_qualified_name,
                render_framework_type=adapter.render_framework_type,
                render_create_index_sqls=adapter.render_create_source_freshness_index_sqls,
            )
    finally:
        adapter.close(connection)
