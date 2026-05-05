"""Tests for planner source column gathering."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models import CompiledProject
from sqlbuild.compiler.planner.helpers.plan_entry import gather_source_columns
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import SourceColumnsTestCase
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_test_project_with_source_entry,
)


class _RecordingAdapter(BaseAdapter):
    def __init__(self, column_names: tuple[str, ...]) -> None:
        self.column_names: tuple[str, ...] = column_names
        self.queried_sql: list[str] = []

    def connect(self, config: dict[str, object]) -> object:
        del config
        return object()

    def close(self, connection: Any) -> None:
        del connection

    def execute(self, connection: Any, sql: str) -> Any:
        del connection, sql
        raise AssertionError("execute should not be called")

    def query_column_names(self, connection: Any, sql: str) -> tuple[str, ...]:
        del connection
        self.queried_sql.append(sql)
        return self.column_names

    def get_all_columns(
        self,
        connection: Any,
        *,
        database: str | None,
        schemas: tuple[str, ...] | None,
        names: tuple[str, ...] | None = None,
    ) -> dict[str, tuple[ColumnInfo, ...]]:
        del connection, database, schemas, names
        return {}


TEST_CASES: list[SourceColumnsTestCase] = [
    SourceColumnsTestCase(
        description="probes enforced expression source query output",
        source_entry=SourceEntry(
            name="raw_payments",
            expression="SELECT 1 AS id, 1700 AS amount_cents, 'success' AS status",
            type_enforcement=True,
        ),
        adapter_column_names=("id", "amount_cents", "status"),
        expected_queried_sql=("SELECT 1 AS id, 1700 AS amount_cents, 'success' AS status",),
        expected_source_column_names=("id", "amount_cents", "status"),
    ),
    SourceColumnsTestCase(
        description="skips non-enforced expression source probe",
        source_entry=SourceEntry(
            name="raw_payments",
            expression="SELECT 1 AS id, 1700 AS amount_cents",
            type_enforcement=None,
        ),
        adapter_column_names=("id", "amount_cents"),
        expected_queried_sql=(),
        expected_source_column_names=(),
    ),
]


@pytest.mark.parametrize("test_case", TEST_CASES, ids=[case.description for case in TEST_CASES])
def test_given_sources_when_gathering_columns_then_returns_expected_source_columns(
    test_case: SourceColumnsTestCase,
) -> None:
    project: CompiledProject = build_test_project_with_source_entry(test_case.source_entry)
    adapter: _RecordingAdapter = _RecordingAdapter(test_case.adapter_column_names)

    result: dict[str, tuple[ColumnInfo, ...]] = gather_source_columns(
        project=project, adapter=adapter, connection=None
    )

    assert tuple(adapter.queried_sql) == test_case.expected_queried_sql
    assert tuple(column.name for column in result.get("raw_payments", ())) == (
        test_case.expected_source_column_names
    )
