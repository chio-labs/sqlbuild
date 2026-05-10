from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason


class FakeCloneAdapter(BaseAdapter):
    def __init__(self, *, supports_zero_copy: bool) -> None:
        self._supports_zero_copy = supports_zero_copy
        self.executed_statements: list[str] = []

    def supports_zero_copy_clone(self) -> bool:
        return self._supports_zero_copy

    def connect(self, config: dict[str, Any]) -> object:
        del config
        return object()

    def close(self, connection: Any) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> None:
        del connection
        self.executed_statements.append(sql)

    def relation_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        del connection, database, schema, name
        return True

    def render_drop(self, *, target: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP TABLE{exists_clause} {target}",)

    def render_clone(
        self,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
    ) -> tuple[str, ...]:
        if hard_copy:
            return (f"CREATE OR REPLACE TABLE {target} AS SELECT * FROM {source}",)
        return (f"CREATE TABLE {target} CLONE {source}",)


def build_clone_model_entry(*, schema: str, name: str) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path("models") / f"{name}.sql",
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        target=CompiledRelationTarget(
            database=None,
            schema=schema,
            name=name,
            qualified_name=f"{schema}.{name}",
        ),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl="MODEL (materialized table);",
    )
