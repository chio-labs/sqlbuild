from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

from sqlbuild.adapter.contract.classes.retention_adapter import RetentionAdapterMixin
from sqlbuild.adapter.contract.models import RelationInfo
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    PlannerRelationsContext,
    PlannerRuntime,
    PlannerScope,
    PlannerWarehouseState,
    WarehouseSnapshot,
)
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    ProjectConfig,
    ResolvedTableType,
    ResolvedTimeTravelRetention,
    TargetConfig,
)
from sqlbuild.spec.contracts.types import (
    TableTypeDowngradePolicy,
    TimeTravelRetentionSource,
)


def build_retention_planner_inputs(
    *,
    adapter: Any,
    desired_days: int,
    existing_relations: dict[str, RelationInfo],
    config_values: dict[str, object],
    table_type: ResolvedTableType | None = None,
    table_type_downgrade: TableTypeDowngradePolicy = TableTypeDowngradePolicy.REQUIRE_CONFIRMATION,
    model_names: tuple[str, ...] = ("orders",),
) -> tuple[PlannerRuntime, PlannerWarehouseState, PlannerScope]:
    models: tuple[CompiledModel, ...] = tuple(
        _retention_model(
            name=name,
            desired_days=desired_days,
            config_values=config_values,
            table_type=table_type,
        )
        for name in model_names
    )
    keys: tuple[CompiledObjectKey, ...] = tuple(model.key for model in models)
    project: CompiledProject = CompiledProject(
        run_id="run-1",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
        models=models,
    )
    scope: PlannerScope = PlannerScope(
        upstream_deps=dict.fromkeys(keys, ()),
        downstream_deps=dict.fromkeys(keys, ()),
        all_keys={model.name: model.key for model in models},
        models_by_name={model.name: model for model in models},
        selected_keys=frozenset(keys),
        execution_order=keys,
    )
    snapshot: WarehouseSnapshot = WarehouseSnapshot(existing_relations=existing_relations)
    warehouse: PlannerWarehouseState = PlannerWarehouseState(
        snapshot=snapshot,
        inspection_relations=PlannerRelationsContext(
            model_locations={},
            seed_locations={},
            function_locations={},
            source_map={},
            source_read_map={},
            source_warehouse_columns={},
            star_exclude_keyword="EXCLUDE",
        ),
    )
    return (
        PlannerRuntime(
            project=project,
            adapter=adapter,
            connection=object(),
            project_config=ProjectConfig(
                name="test",
                adapter=str(adapter.adapter_name),
                targets={"test": TargetConfig(table_type_downgrade=table_type_downgrade)},
            ),
            local_config=LocalConfig(),
        ),
        warehouse,
        scope,
    )


def retention_mock_adapter(**attributes: Any) -> Mock:
    """Return a Mock adapter whose batched retention hooks use the real default implementations."""

    adapter: Mock = Mock(**attributes)
    adapter.inspect_retentions.side_effect = lambda *, connection, requests: (
        RetentionAdapterMixin.inspect_retentions(adapter, connection=connection, requests=requests)
    )
    adapter.retention_state_from_relation.side_effect = lambda *, request, relation: (
        RetentionAdapterMixin.retention_state_from_relation(
            adapter, request=request, relation=relation
        )
    )
    return adapter


def _retention_model(
    *,
    name: str,
    desired_days: int,
    config_values: dict[str, object],
    table_type: ResolvedTableType | None,
) -> CompiledModel:
    return CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        deps=(),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        query_sql="SELECT 1 AS order_id",
        config=CompileModelConfig(
            values=config_values,
            time_travel_retention=ResolvedTimeTravelRetention(
                desired_days=desired_days,
                unmanaged=False,
                source=TimeTravelRetentionSource.MODEL,
            ),
            table_type=table_type or ResolvedTableType(),
        ),
        destination=CompiledRelationLocation(
            database="warehouse",
            schema="analytics",
            name=name,
            qualified_name=f"warehouse.analytics.{name}",
        ),
    )
