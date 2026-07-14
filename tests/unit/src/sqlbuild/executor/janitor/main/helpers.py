"""Test helpers for janitor executor tests."""

from __future__ import annotations

import base64
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.classes.statement_recorder import StatementRecorder
from sqlbuild.adapter.contract.models import (
    ColumnInfo,
    CursorValue,
    RelationInfo,
    RowDiffResult,
    RowDiffTolerances,
    SchemaDiffResult,
)
from sqlbuild.adapter.contract.types import TablePromotionMode
from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledRelationLocation,
    CompiledSeed,
    CompiledSource,
    CompileModelConfig,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.fingerprints.constants import FINGERPRINT_TABLE_NAME
from sqlbuild.compiler.source_freshness.constants import SOURCE_FRESHNESS_TABLE_NAME
from sqlbuild.spec.contracts.constants import DEFAULT_SEED_CSV_SETTINGS
from sqlbuild.spec.contracts.models import SchemaSeedEntry, SeedCsvSettings, SourceEntry


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
        self.executed_sql: list[str] = []
        self.tracked_relations: tuple[tuple[str | None, str | None, str], ...] = tracked_relations
        self._tracked_rows: tuple[tuple[Any, ...], ...] = tuple(
            (
                "model",
                tracked_relation[2],
                tracked_relation[0],
                tracked_relation[1],
                tracked_relation[2],
                "run_001",
                "definition_hash",
                "version_hash",
                "schema_hash",
                base64.b64encode(b"SELECT 1").decode("ascii"),
                base64.b64encode(b"{}").decode("ascii"),
                "2026-01-15T12:00:00",
            )
            for tracked_relation in tracked_relations
        )
        tracked_locations: set[tuple[str | None, str | None]] = {
            (tracked[0], tracked[1]) for tracked in tracked_relations
        }
        self._available_relations: tuple[RelationInfo, ...] = (
            *relation_infos,
            *tuple(
                RelationInfo(
                    database=database,
                    schema=schema,
                    name=FINGERPRINT_TABLE_NAME,
                    relation_type="base table",
                )
                for database, schema in tracked_locations
            ),
        )
        relation_keys: set[tuple[str | None, str | None, str]] = {
            (relation.database, relation.schema, relation.name)
            for relation in self._available_relations
        }
        state_relation_keys: set[tuple[str | None, str | None, str]] = {
            (relation.database, relation.schema, state_name)
            for relation in self._available_relations
            for state_name in (FINGERPRINT_TABLE_NAME, SOURCE_FRESHNESS_TABLE_NAME)
        }
        self._existing_relation_keys = relation_keys & state_relation_keys

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
        self.executed_sql.append(sql)
        rows_by_query_kind: dict[bool, tuple[tuple[Any, ...], ...]] = {
            True: (),
            False: self._tracked_rows,
        }
        return _FakeResult(rows=rows_by_query_kind["LIMIT 0" in sql])

    def list_relations(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> tuple[RelationInfo, ...]:
        selected: list[RelationInfo] = []
        available_schemas: tuple[str, ...] = schemas or tuple(
            relation.schema or "" for relation in self._available_relations
        )
        available_names: tuple[str, ...] = names or tuple(
            relation.name for relation in self._available_relations
        )
        for relation in self._available_relations:
            _APPEND_RELATION_BY_SELECTED[
                relation.database == database
                and (relation.schema or "") in available_schemas
                and relation.name in available_names
            ](selected, relation)
        return tuple(selected)

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
        del connection
        return (database, schema, name) in self._existing_relation_keys

    def render_prune_fingerprint_history_sql(
        self,
        *,
        database: str | None,
        schema: str,
        retain_versions: int,
    ) -> str:
        del database, schema
        return f"PRUNE {FINGERPRINT_TABLE_NAME} KEEP {retain_versions}"

    def render_prune_source_freshness_history_sql(
        self,
        *,
        database: str | None,
        schema: str,
        retain_versions: int,
    ) -> str:
        del database, schema
        return f"PRUNE {SOURCE_FRESHNESS_TABLE_NAME} KEEP {retain_versions}"

    def drop(
        self,
        connection: Any,
        *,
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists, statement_recorder
        self.dropped_targets.append(destination)

    def create_table_as(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        config: dict[str, Any] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def create_view_as(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def append(
        self,
        connection: Any,
        *,
        destination: str,
        sql: str,
        columns: tuple[str, ...] | None = None,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def delete_insert(
        self,
        connection: Any,
        *,
        destination: str,
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
        destination: str,
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
        destination: str,
        sql: str,
        unique_key: str | tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def load_seed(
        self,
        connection: Any,
        *,
        destination: str,
        file_path: Path,
        columns: tuple[ColumnInfo, ...],
        csv_settings: SeedCsvSettings = DEFAULT_SEED_CSV_SETTINGS,
        replace: bool = True,
        infer_types: bool = False,
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def add_columns(
        self,
        connection: Any,
        *,
        destination: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def drop_columns(
        self,
        connection: Any,
        *,
        destination: str,
        column_names: tuple[str, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def alter_column_types(
        self,
        connection: Any,
        *,
        destination: str,
        columns: tuple[ColumnInfo, ...],
        statement_recorder: StatementRecorder,
    ) -> None:
        raise NotImplementedError

    def rename(
        self,
        connection: Any,
        *,
        origin: str,
        destination: str,
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
        origin: str,
        destination: str,
        hard_copy: bool = False,
        origin_is_transient: bool = False,
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
        origin: str,
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
        destination: str,
        if_exists: bool = True,
        statement_recorder: StatementRecorder,
    ) -> None:
        del connection, if_exists, statement_recorder
        self.dropped_targets.append(destination)
        raise RuntimeError(self.message)


class _FakeResult:
    def __init__(self, *, rows: tuple[tuple[Any, ...], ...]) -> None:
        self.rows: tuple[tuple[Any, ...], ...] = rows

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self.rows)


def build_project(*, source_schema: str | None = None) -> CompiledProject:
    source: CompiledSource = CompiledSource(
        key=CompiledObjectKey(
            resource_type=CompiledResourceType.SOURCE,
            name="raw_orders",
        ),
        deps=(),
        name="raw_orders",
        source_entry=SourceEntry(name="raw_orders", schema=source_schema or "", table="orders"),
        source_file=cast(Any, object()),
    )
    sources: tuple[CompiledSource, ...] = {True: (), False: (source,)}[source_schema is None]
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
                destination=CompiledRelationLocation(
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
                destination=CompiledRelationLocation(
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


def _append_relation(selected: list[RelationInfo], relation: RelationInfo) -> None:
    selected.append(relation)


def _ignore_relation(selected: list[RelationInfo], relation: RelationInfo) -> None:
    del selected, relation


_APPEND_RELATION_BY_SELECTED: dict[bool, Callable[[list[RelationInfo], RelationInfo], None]] = {
    True: _append_relation,
    False: _ignore_relation,
}
