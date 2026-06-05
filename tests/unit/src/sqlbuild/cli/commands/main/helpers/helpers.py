from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlbuild.adapter.shared.types import FrameworkType
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationDestination,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import ModelPlanEntry
from sqlbuild.compiler.planner.types import MaterializationType, PlanAction, PlanReason
from sqlbuild.compiler.source_freshness.models import (
    SourceFreshnessIdentity,
    SourceFreshnessRecord,
)


class RecordingAdapter:
    def __init__(self) -> None:
        self.insert_count: int = 0

    def connect(self, _config: dict[str, object]) -> object:
        return object()

    def close(self, _connection: object) -> None:
        return None

    def execute(self, _connection: object, sql: str) -> None:
        if sql.strip().upper().startswith("INSERT"):
            self.insert_count += 1

    def render_qualified_name(
        self, *, database: str | None, schema: str | None, name: str
    ) -> str | None:
        if schema is None:
            return name
        if database is not None:
            return f"{database}.{schema}.{name}"
        return f"{schema}.{name}"

    def render_framework_type(self, framework_type: FrameworkType) -> str:
        return framework_type.value


def model_entry(name: str) -> ModelPlanEntry:
    return ModelPlanEntry(
        key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=name),
        name=name,
        relative_path=Path(f"models/{name}.sql"),
        materialization_type=MaterializationType.TABLE,
        action=PlanAction.CREATE_TABLE,
        reason=PlanReason.NO_CHANGE,
        destination=CompiledRelationDestination(
            database=None,
            schema="main",
            name=name,
            qualified_name=f"main.{name}",
        ),
        fingerprint_query_sql="SELECT 1",
        resolved_sql="SELECT 1",
        logical_ddl="",
    )


def source_freshness_identity() -> SourceFreshnessIdentity:
    return SourceFreshnessIdentity(
        source_name="raw_orders",
        target_database=None,
        target_schema=None,
        target_name=None,
    )


def source_freshness_record() -> SourceFreshnessRecord:
    return SourceFreshnessRecord(
        source_name="raw_orders",
        target_database=None,
        target_schema=None,
        target_name=None,
        run_id="planning",
        strategy="sql",
        value_kind="integer",
        data_version="1",
        data_version_hash="hash",
        observed_at=datetime(2026, 1, 1, 0, 0, 0),
    )
