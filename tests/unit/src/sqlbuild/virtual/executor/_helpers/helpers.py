from __future__ import annotations

from pathlib import Path

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import (
    BackfillResult,
    CursorBounds,
    ModelPlanEntry,
    PlanOutput,
)
from sqlbuild.compiler.planner.types import (
    BackfillAction,
    MaterializationType,
    PlanAction,
    PlanReason,
)
from sqlbuild.spec.contracts.models import SettingsConfig
from sqlbuild.virtual.state.models import PhysicalRelationRecord
from sqlbuild.virtual.state.types import PhysicalArtifactType


def build_relation_location(*, schema: str, name: str) -> CompiledRelationLocation:
    return CompiledRelationLocation(
        database=None,
        schema=schema,
        name=name,
        qualified_name=f"{schema}.{name}",
    )


class SeedPhysicalRelationTestBackend:
    def __init__(self, *, available_seed_names: tuple[str, ...]) -> None:
        self.available_seed_names: frozenset[str] = frozenset(available_seed_names)

    def get_physical_relation_for_artifact(
        self,
        *,
        connection: object,
        schema: str,
        artifact_type: PhysicalArtifactType,
        artifact_name: str,
        version_hash: str,
    ) -> PhysicalRelationRecord | None:
        del connection, schema, artifact_type
        relation: PhysicalRelationRecord = build_seed_physical_relation(
            seed_name=artifact_name, version_hash=version_hash
        )
        return (None, relation)[artifact_name in self.available_seed_names]


def build_virtual_executor_test_project() -> CompiledProject:
    stg_orders: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="stg_orders"),
        deps=(),
        name="stg_orders",
        relative_path=Path("models/stg_orders.sql"),
        query_sql="SELECT 1 AS id",
        config=CompileModelConfig(values={"materialized": "table"}),
        destination=CompiledRelationLocation(
            database=None,
            schema="dev",
            name="stg_orders",
            qualified_name="dev.stg_orders",
        ),
    )
    fact_orders: CompiledModel = CompiledModel(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="fact_orders"),
        deps=(stg_orders.key,),
        name="fact_orders",
        relative_path=Path("models/fact_orders.sql"),
        query_sql='SELECT id FROM __ref("stg_orders")',
        config=CompileModelConfig(values={"materialized": "table"}),
        destination=CompiledRelationLocation(
            database=None,
            schema="dev",
            name="fact_orders",
            qualified_name="dev.fact_orders",
        ),
    )
    return CompiledProject(
        run_id="test_run",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        settings=SettingsConfig(),
        models=(stg_orders, fact_orders),
    )


def build_bound_physical_relation(*, model_name: str, version_hash: str) -> PhysicalRelationRecord:
    return PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name=model_name,
        version_hash=version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=f"{model_name}__v_{version_hash[:8]}",
        relation_type="table",
    )


def build_seed_physical_relation(*, seed_name: str, version_hash: str) -> PhysicalRelationRecord:
    return PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.SEED,
        artifact_name=seed_name,
        version_hash=version_hash,
        database_name=None,
        schema_name="dev__sqb_physical",
        relation_name=f"{seed_name}__v_{version_hash[:8]}",
        relation_type="table",
    )


def build_optional_bound_physical_relations(
    *, model_name: str, version_hash: str | None
) -> dict[str, PhysicalRelationRecord]:
    relations: dict[str, PhysicalRelationRecord] = {
        model_name: build_bound_physical_relation(
            model_name=model_name, version_hash=version_hash or ""
        )
    }
    return ({}, relations)[version_hash is not None]


def build_adapter() -> DuckDbAdapter:
    return DuckDbAdapter()


def build_seeded_incremental_plan_output(
    *,
    incremental_strategy: str,
    resolved_sql: str = "SELECT id, ordered_at, amount_cents + 1 AS amount_cents FROM raw",
    materialization_type: MaterializationType = MaterializationType.INCREMENTAL,
    action: PlanAction = PlanAction.CREATE_TABLE,
    cursor_bounds: CursorBounds | None = None,
    include_cursor_bounds: bool = True,
) -> PlanOutput:
    default_cursor_bounds: CursorBounds | None = (
        None,
        CursorBounds(start="2026-01-02T00:00:00", end="2026-01-04T00:00:00"),
    )[include_cursor_bounds]
    effective_cursor_bounds: CursorBounds | None = (default_cursor_bounds, cursor_bounds)[
        cursor_bounds is not None
    ]
    entry: ModelPlanEntry = ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
        name="orders",
        relative_path=Path("models/orders.sql"),
        materialization_type=materialization_type,
        action=action,
        reason=PlanReason.QUERY_CHANGED,
        destination=CompiledRelationLocation(
            database=None,
            schema="dev__sqb_physical",
            name="orders__v_newhash",
            qualified_name='"dev__sqb_physical"."orders__v_newhash"',
        ),
        fingerprint_query_sql=resolved_sql,
        resolved_sql=resolved_sql,
        logical_ddl="",
        incremental_strategy=incremental_strategy,
        cursor_column="ordered_at",
        cursor_type="timestamp",
        cursor_bounds=effective_cursor_bounds,
        backfill=BackfillResult(action=BackfillAction.BOUNDED, duration="7d"),
    )
    return PlanOutput(model_entries=(entry,))
