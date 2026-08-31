"""Test helpers for build CLI helper tests."""

from pathlib import Path

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry, TableTypePlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason


def build_snapshot_full_refresh_entry(
    *,
    name: str = "customer_snapshot",
    observed_at_column: str | None = None,
    snapshot_full_refresh: str | None = None,
) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.SNAPSHOT,
        action=PlanAction.SNAPSHOT,
        reason=PlanReason.FULL_REFRESH,
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name=name,
            qualified_name=f"main.{name}",
        ),
        fingerprint_query_sql="SELECT 1 AS id",
        resolved_sql="SELECT 1 AS id",
        logical_ddl=f"CREATE TABLE main.{name} AS SELECT 1 AS id",
        observed_at_column=observed_at_column,
        snapshot_full_refresh=snapshot_full_refresh,
    )


def build_table_type_entry(
    *,
    name: str = "orders",
    downgrade: bool = True,
    policy: str = "require_confirmation",
    desired_type: str = "transient",
    actual_type: str = "permanent",
) -> TableTypePlanEntry:
    return TableTypePlanEntry(
        model_name=name,
        destination=CompiledRelationLocation(
            database=None,
            schema="main",
            name=name,
            qualified_name=f"main.{name}",
        ),
        copy_name=f"__sqb_type_swap__{name}",
        desired_type=desired_type,
        actual_type=actual_type,
        source="model",
        downgrade=downgrade,
        downgrade_policy=policy,
    )
