"""Test helpers for janitor executor tests."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    CursorValue,
    RelationInfo,
    RowDiffResult,
    RowDiffTolerances,
    SchemaDiffResult,
    StatementRecorder,
)
from sqlbuild.adapter.shared.types import TablePromotionMode
from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationDestination,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.spec.models.schema import SchemaSeedEntry, SeedCsvSettings, default_seed_csv_settings
from sqlbuild.spec.models.source import SourceEntry


class FakeJanitorAdapter(BaseAdapter):
    def __init__(
        self,
        *,
        relation_infos: tuple[RelationInfo, ...],
        supports_age_metadata: bool = True,
        tracked_relations: tuple[tuple[str | None, str | None, str], ...] = (),
    ) -> None:
        self.relation_infos: tuple[RelationInfo, ...] = relation_infos
        self.age_metadata_supported: bool = supports_age_metadata
        self.dropped_targets: list[str] = []
        self.tracked_relations: tuple[tuple[str | None, str | None, str], ...] = tracked_relations

    def supports_relation_age_metadata(self) -> bool:
        return self.age_metadata_supported

    def default_schema(self) -> str | None:
        return "analytics"

    def default_database(self) -> str | None:
        return None

    def star_exclude_keyword(self) -> str:
        return "EXCLUDE"

    def default_table_promotion_mode(self) -> TablePromotionMode:
        return TablePromotionMode.STAGED

    def connect(self, config: dict[str, Any]) -> object:
        return object()

    def close(self, connection: Any) -> None:
        return None

    def execute(self, connection: Any, sql: str) -> Any:
        del connection
        if "LIMIT 0" in sql:
            return _FakeResult(rows=())
        rows: list[tuple[Any, ...]] = []
        tracked_relation: tuple[str | None, str | None, str]
        for tracked_relation in self.tracked_relations:
            rows.append(
                (
                    tracked_relation[2],
                    tracked_relation[0],
                    tracked_relation[1],
                    tracked_relation[2],
                    "run_001",
                    "query_hash",
                    "version_hash",
                    "schema_hash",
                    base64.b64encode(b"SELECT 1").decode("ascii"),
                    base64.b64encode(b"{}").decode("ascii"),
                    "2026-01-15T12:00:00",
                )
            )
        return _FakeResult(rows=tuple(rows))

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        return tuple(
            relation
            for relation in self.relation_infos
            if relation.database == database
            and (schemas is None or relation.schema in schemas)
            and (not names or relation.name in names)
        )

    def get_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> tuple[ColumnInfo, ...]:
        return ()

    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        return {}

    def relation_exists(
        self,
        connection: Any,
        *,
        database: str | None,
        schema: str | None,
        name: str,
    ) -> bool:
        return False

    def drop(
        self,
        connection: Any,
        *,
        target: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists, statement_recorder
        self.dropped_targets.append(target)

    def create_table_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def create_view_as(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def append(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def delete_insert(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def delete_insert_cursor(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def merge(
        self,
        connection: Any,
        *,
        target: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def load_seed(
        self,
        connection: Any,
        *,
        target: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = default_seed_csv_settings,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def add_columns(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def drop_columns(
        self,
        connection: Any,
        *,
        target: str,
        column_names: tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def alter_column_types(
        self,
        connection: Any,
        *,
        target: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def rename(
        self,
        connection: Any,
        *,
        source: str,
        target: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def swap(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def clone(
        self,
        connection: Any,
        *,
        source: str,
        target: str,
        hard_copy: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def diff_schema(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
    ) -> SchemaDiffResult:
        raise NotImplementedError

    def diff_rows(
        self,
        connection: Any,
        *,
        left: str,
        right: str,
        unique_key: str | tuple[str, ...],
        excluded_columns: tuple[str, ...] = (),
        tolerances: RowDiffTolerances | None = None,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> RowDiffResult:
        raise NotImplementedError

    def count_rows(
        self,
        connection: Any,
        *,
        relation: str,
        cursor_column: str | None = None,
        start_cursor: CursorValue | None = None,
        end_cursor: CursorValue | None = None,
    ) -> int:
        raise NotImplementedError

    def relation_names_match(self, left: str, right: str) -> bool:
        return left == right

    def render_query_with_cursor_bounds(
        self,
        *,
        sql: str,
        cursor_column: str,
        cursor_start: str,
        cursor_end: str | None,
        cursor_type: object,
    ) -> str:
        raise NotImplementedError

    def render_seed_select_before_cursor(
        self,
        *,
        source: str,
        cursor_column: str,
        cursor_end_exclusive: str,
        cursor_type: object,
    ) -> str:
        raise NotImplementedError


class FailingDropAdapter(FakeJanitorAdapter):
    def __init__(self, *, message: str) -> None:
        super().__init__(relation_infos=())
        self.message: str = message

    def drop(
        self,
        connection: Any,
        *,
        target: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists, statement_recorder
        self.dropped_targets.append(target)
        raise RuntimeError(self.message)


class _FakeResult:
    def __init__(self, *, rows: tuple[tuple[Any, ...], ...]) -> None:
        self.rows: tuple[tuple[Any, ...], ...] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


def build_project(*, source_schema: str | None = None) -> CompiledProject:
    sources: tuple[CompiledSource, ...] = ()
    if source_schema is not None:
        sources = (
            CompiledSource(
                key=CompiledObjectKey(
                    resource_type=CompiledResourceType.SOURCE,
                    name="raw_orders",
                ),
                deps=(),
                name="raw_orders",
                source_entry=SourceEntry(name="raw_orders", schema=source_schema, table="orders"),
                source_file=cast(Any, object()),
            ),
        )
    return CompiledProject(
        run_id="run-1",
        effective_target_name="dev",
        effective_connection={},
        effective_vars={},
        models=(
            CompiledModel(
                key=CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name="orders"),
                deps=(),
                name="orders",
                relative_path=Path("models/orders.sql"),
                query_sql="select 1",
                config=CompileModelConfig(),
                destination=CompiledRelationDestination(
                    database=None,
                    schema="analytics",
                    name="orders",
                    qualified_name="analytics.orders",
                ),
            ),
        ),
        seeds=(
            CompiledSeed(
                key=CompiledObjectKey(resource_type=CompiledResourceType.SEED, name="countries"),
                deps=(),
                name="countries",
                seed_file=cast(Any, object()),
                schema_entry=SchemaSeedEntry(name="countries"),
                schema_file=cast(Any, object()),
                destination=CompiledRelationDestination(
                    database=None,
                    schema="analytics",
                    name="countries",
                    qualified_name="analytics.countries",
                ),
            ),
        ),
        sources=sources,
    )


def relation_info_for_test(*, schema: str, name: str) -> RelationInfo:
    return RelationInfo(
        database=None,
        schema=schema,
        name=name,
        relation_type="table",
        created_at=None,
        last_altered_at=None,
    )
