from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.classes.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationLocation
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry, PlanOutput
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason


class RelationTargetTestAdapter(BaseAdapter):
    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> object:
        del connection
        return sql


def build_plan_output_with_model(name: str = "orders") -> PlanOutput:
    entry: ModelPlanEntry = ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None, schema="main", name=name, qualified_name=f"main.{name}"
        ),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl="CREATE TABLE main.orders AS SELECT 1",
    )
    return PlanOutput(
        execution_order=(entry.key,),
        model_entries=(entry,),
        selected_keys=frozenset((entry.key,)),
    )
