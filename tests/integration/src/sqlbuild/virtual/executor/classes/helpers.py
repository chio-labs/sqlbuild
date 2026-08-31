"""Helpers for virtual executor class integration tests."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import (
    IncrementalMode,
    MaterializationType,
    PlanAction,
    PlanReason,
)


def build_virtual_microbatch_lease_entry(
    *,
    action: PlanAction = PlanAction.INCREMENTAL_DELETE_INSERT,
    incremental_strategy: str = "delete_insert",
    incremental_mode: str | None = IncrementalMode.MICROBATCH,
) -> ModelPlanEntry:
    """Build a virtual microbatch entry for lease-manager tests."""

    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        name="orders",
        relative_path=Path("models/orders.sql"),
        materialization_type=MaterializationType.INCREMENTAL,
        action=action,
        reason=PlanReason.NORMAL_INCREMENTAL,
        destination=CompiledRelationLocation(
            database=None,
            schema="dev__sqb_physical",
            name="orders__v_f2",
            qualified_name="dev__sqb_physical.orders__v_f2",
        ),
        fingerprint_query_sql="SELECT 1 AS id",
        resolved_sql="SELECT 1 AS id",
        logical_ddl="",
        incremental_strategy=incremental_strategy,
        incremental_mode=incremental_mode,
    )
