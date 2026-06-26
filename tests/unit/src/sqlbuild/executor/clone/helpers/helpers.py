from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import RelationInfo
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason


class FakeCloneAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        supports_zero_copy: bool,
        origin_is_transient: bool = False,
        origin_names: tuple[str, ...] = ("fact_orders",),
    ) -> None:
        self._supports_zero_copy = supports_zero_copy
        self._origin_is_transient = origin_is_transient
        self._origin_names = origin_names
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

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        del connection, database, names
        if schemas is None:
            return ()
        return tuple(
            RelationInfo(
                database=None,
                schema=schema,
                name=origin_name,
                relation_type="base table",
                is_transient=self._origin_is_transient,
            )
            for schema in schemas
            for origin_name in self._origin_names
        )

    def render_drop(self, *, destination: str, if_exists: bool = True) -> tuple[str, ...]:
        exists_clause: str = " IF EXISTS" if if_exists else ""
        return (f"DROP TABLE{exists_clause} {destination}",)

    def render_clone(
        self,
        *,
        origin: str,
        destination: str,
        hard_copy: bool = False,
        origin_is_transient: bool = False,
    ) -> tuple[str, ...]:
        if hard_copy:
            return (f"CREATE OR REPLACE TABLE {destination} AS SELECT * FROM {origin}",)
        table_kind: str = "TRANSIENT TABLE" if origin_is_transient else "TABLE"
        return (f"CREATE {table_kind} {destination} CLONE {origin}",)


def build_clone_model_entry(*, schema: str, name: str) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path("models") / f"{name}.sql",
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.FIRST_RUN,
        destination=CompiledRelationLocation(
            database=None,
            schema=schema,
            name=name,
            qualified_name=f"{schema}.{name}",
        ),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl="MODEL (materialized table);",
    )
