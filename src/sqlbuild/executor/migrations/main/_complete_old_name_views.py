"""Keep a migrated model's old name working after its successful build."""

from __future__ import annotations

from typing import Any

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.migrations._helpers.old_name_views import (
    rebind_old_name_views_atomically,
    run_planned_old_name_steps,
    views_reading,
)


def complete_old_name_views(
    *,
    plan: PlanOutput,
    adapter: BaseAdapter,
    connection: Any,
    model_name: str,
    destination: CompiledRelationLocation,
    run_id: str,
) -> tuple[str, ...]:
    """Run pending old-name steps, then rebind every compatibility view reading the model."""

    warnings: tuple[str, ...] = run_planned_old_name_steps(
        plan=plan, adapter=adapter, connection=connection, model_name=model_name, run_id=run_id
    )
    _ = rebind_old_name_views_atomically(
        adapter=adapter,
        connection=connection,
        sources=views_reading(location=destination, recorded_views=plan.old_name_views),
    )
    return warnings
