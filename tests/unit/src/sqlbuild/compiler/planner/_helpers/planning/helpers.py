from __future__ import annotations

from pathlib import Path
from typing import Any

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
) -> tuple[PlannerRuntime, PlannerWarehouseState, PlannerScope]:
    key: CompiledObjectKey = CompiledObjectKey(
        resource_type=CompiledResourceType.MODEL,
        name="orders",
    )
    model: CompiledModel = CompiledModel(
        key=key,
        deps=(),
        name="orders",
        relative_path=Path("models/orders.sql"),
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
            name="orders",
            qualified_name="warehouse.analytics.orders",
        ),
    )
    project: CompiledProject = CompiledProject(
        run_id="run-1",
        effective_target_name="test",
        effective_connection={},
        effective_vars={},
        models=(model,),
    )
    scope: PlannerScope = PlannerScope(
        upstream_deps={key: ()},
        downstream_deps={key: ()},
        all_keys={model.name: key},
        models_by_name={model.name: model},
        selected_keys=frozenset({key}),
        execution_order=(key,),
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
