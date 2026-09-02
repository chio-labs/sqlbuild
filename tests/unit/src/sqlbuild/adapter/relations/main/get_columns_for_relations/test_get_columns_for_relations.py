from __future__ import annotations

from typing import Any, ClassVar

import pytest

from sqlbuild.adapter.contract.classes.base_adapter import BaseAdapter
from sqlbuild.adapter.contract.models import ColumnInfo, RelationInfo
from tests.unit.src.sqlbuild.adapter.relations.main.get_columns_for_relations._test_types import (
    QualifiedBulkColumnsTestCase,
)


class _BulkRecordingAdapter(BaseAdapter):
    adapter_name: ClassVar[str] = "bulk-recording-test"

    def __init__(self) -> None:
        self.queries: list[tuple[str | None, tuple[str, ...] | None, tuple[str, ...] | None]] = []
        self.inventory_names: dict[tuple[str | None, str], tuple[str, ...]] = {}

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: object) -> None:
        del connection

    def _execute(self, connection: Any, sql: str) -> object:
        del connection
        return sql

    def get_all_columns(
        self,
        *,
        connection: Any,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        del connection
        self.queries.append((database, schemas, names))
        schema: str = "none" if schemas is None else schemas[0]
        requested_names: tuple[str, ...] = (
            self.inventory_names.get((database, schema), ()) if names is None else names
        )
        return {
            name: (ColumnInfo(name="id", type=f"{database}.{schema}.{name}"),)
            for name in requested_names
        }


@pytest.mark.parametrize(
    "test_case",
    [
        QualifiedBulkColumnsTestCase(
            description="groups bulk reads by database and schema without identity collisions",
            expected_query_count=3,
            expected_identity_count=4,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_qualified_relations_when_getting_columns_then_groups_bulk_queries_and_keys_results(
    test_case: QualifiedBulkColumnsTestCase,
) -> None:
    relations: tuple[RelationInfo, ...] = (
        RelationInfo(database="DB_A", schema="SCHEMA_A", name="SHARED", relation_type="table"),
        RelationInfo(database="DB_A", schema="SCHEMA_A", name="ORDERS", relation_type="table"),
        RelationInfo(database="DB_A", schema="SCHEMA_B", name="SHARED", relation_type="view"),
        RelationInfo(database="DB_B", schema="SCHEMA_A", name="SHARED", relation_type="table"),
    )
    adapter: _BulkRecordingAdapter = _BulkRecordingAdapter()

    columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(connection=object(), relations=relations)
    )

    assert len(adapter.queries) == test_case.expected_query_count
    assert len(columns) == test_case.expected_identity_count
    assert columns[("db_a", "schema_a", "shared")][0].type == "DB_A.SCHEMA_A.SHARED"
    assert columns[("db_a", "schema_b", "shared")][0].type == "DB_A.SCHEMA_B.SHARED"
    assert columns[("db_b", "schema_a", "shared")][0].type == "DB_B.SCHEMA_A.SHARED"


@pytest.mark.parametrize(
    "test_case",
    [
        QualifiedBulkColumnsTestCase(
            description="broad scope above 250 relations uses unrestricted bulk metadata query",
            expected_query_count=1,
            expected_identity_count=251,
            expected_names_filter_is_none=True,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_broad_relation_scope_when_getting_columns_then_preserves_unrestricted_bulk_query(
    test_case: QualifiedBulkColumnsTestCase,
) -> None:
    relation_names: tuple[str, ...] = tuple(f"RELATION_{index}" for index in range(251))
    relations: tuple[RelationInfo, ...] = tuple(
        RelationInfo(
            database="DB_A",
            schema="SCHEMA_A",
            name=name,
            relation_type="table",
        )
        for name in relation_names
    )
    adapter: _BulkRecordingAdapter = _BulkRecordingAdapter()
    adapter.inventory_names[("DB_A", "SCHEMA_A")] = relation_names

    columns: dict[tuple[str | None, str | None, str], tuple[ColumnInfo, ...]] = (
        adapter.get_columns_for_relations(connection=object(), relations=relations)
    )

    assert len(adapter.queries) == test_case.expected_query_count
    assert len(columns) == test_case.expected_identity_count
    assert (adapter.queries[0][2] is None) is test_case.expected_names_filter_is_none
