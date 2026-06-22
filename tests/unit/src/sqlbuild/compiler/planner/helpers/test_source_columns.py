"""Tests for planner source column gathering."""

from __future__ import annotations

from typing import Any

import pytest

from sqlbuild.adapter.base.base_adapter import BaseAdapter
from sqlbuild.adapter.shared.models import ColumnInfo
from sqlbuild.compiler.compile.models.core import CompiledModel, CompiledProject
from sqlbuild.compiler.planner.exceptions import PlannerInputError
from sqlbuild.compiler.planner.helpers.output.plan_entry import (
    gather_source_columns,
    validate_source_cursor_input_columns,
)
from sqlbuild.shared.types import SqlReferenceKind
from sqlbuild.spec.models.source import SourceEntry
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    SourceColumnsTestCase,
    SourceCursorInputColumnsTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_cursor_input_contract_models,
    build_cursor_input_contract_sources,
    build_source_cursor_input_model,
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

CURSOR_INPUT_TEST_CASES: list[SourceCursorInputColumnsTestCase] = [
    SourceCursorInputColumnsTestCase(
        description="passes when source cursor input column is known",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "loaded_at"},
        source_columns={"raw_orders": ("order_id", "loaded_at")},
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="passes when default source cursor column is known",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs=None,
        source_columns={"raw_orders": ("order_id", "event_time")},
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="skips when source columns are unknown",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "missing_loaded_at"},
        source_columns={},
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="skips dbt ref cursor input validation",
        reference_kind=SqlReferenceKind.DBT_REF,
        reference_name="dbt_orders",
        cursor_column="event_time",
        cursor_inputs={"dbt_orders": "missing_loaded_at"},
        source_columns={"dbt_orders": ("order_id", "event_time")},
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="skips model ref cursor input validation",
        reference_kind=SqlReferenceKind.REF,
        reference_name="stg_orders",
        cursor_column="event_time",
        cursor_inputs={"stg_orders": "missing_loaded_at"},
        source_columns={"stg_orders": ("order_id", "event_time")},
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="passes when enforced model contract declares cursor input column",
        reference_kind=SqlReferenceKind.REF,
        reference_name="stg_orders",
        cursor_column="event_time",
        cursor_inputs={"stg_orders": "loaded_at"},
        source_columns={},
        upstream_contract="enforced",
        upstream_declared_columns=("order_id", "loaded_at"),
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="skips non-enforced model contract cursor input validation",
        reference_kind=SqlReferenceKind.REF,
        reference_name="stg_orders",
        cursor_column="event_time",
        cursor_inputs={"stg_orders": "missing_loaded_at"},
        source_columns={},
        upstream_contract="none",
        upstream_declared_columns=("order_id",),
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="passes when enforced source contract declares cursor input column",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "loaded_at"},
        source_columns={},
        upstream_contract="enforced",
        upstream_declared_columns=("order_id", "loaded_at"),
        expected_valid=True,
    ),
    SourceCursorInputColumnsTestCase(
        description="skips non-enforced source contract cursor input validation",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "missing_loaded_at"},
        source_columns={},
        upstream_contract="none",
        upstream_declared_columns=("order_id",),
        expected_valid=True,
    ),
]

CURSOR_INPUT_ERROR_TEST_CASES: list[SourceCursorInputColumnsTestCase] = [
    SourceCursorInputColumnsTestCase(
        description="raises when source cursor input column is missing",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "missing_loaded_at"},
        source_columns={"raw_orders": ("order_id", "event_time")},
        expected_valid=False,
        expected_error_fragment=(
            "model 'test_model': cursor_inputs references source 'raw_orders' column "
            "'missing_loaded_at'"
        ),
    ),
    SourceCursorInputColumnsTestCase(
        description="raises when enforced model contract omits cursor input column",
        reference_kind=SqlReferenceKind.REF,
        reference_name="stg_orders",
        cursor_column="event_time",
        cursor_inputs={"stg_orders": "missing_loaded_at"},
        source_columns={},
        upstream_contract="enforced",
        upstream_declared_columns=("order_id", "event_time"),
        expected_valid=False,
        expected_error_fragment="model contract does not expose the column",
    ),
    SourceCursorInputColumnsTestCase(
        description="raises when enforced source contract omits cursor input column",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "missing_loaded_at"},
        source_columns={},
        upstream_contract="enforced",
        upstream_declared_columns=("order_id", "event_time"),
        expected_valid=False,
        expected_error_fragment="source contract does not expose the column",
    ),
    SourceCursorInputColumnsTestCase(
        description="raises when enforced source contract omits physical extra column",
        reference_kind=SqlReferenceKind.SOURCE,
        reference_name="raw_orders",
        cursor_column="event_time",
        cursor_inputs={"raw_orders": "extra_loaded_at"},
        source_columns={"raw_orders": ("order_id", "extra_loaded_at")},
        upstream_contract="enforced",
        upstream_declared_columns=("order_id",),
        expected_valid=False,
        expected_error_fragment="source contract does not expose the column",
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


@pytest.mark.parametrize(
    "test_case",
    CURSOR_INPUT_TEST_CASES,
    ids=[case.description for case in CURSOR_INPUT_TEST_CASES],
)
def test_given_valid_cursor_input_source_columns_when_validating_then_passes(
    test_case: SourceCursorInputColumnsTestCase,
) -> None:
    model: CompiledModel = build_source_cursor_input_model(test_case)
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = {
        source_name: tuple(ColumnInfo(name=name, type="") for name in column_names)
        for source_name, column_names in test_case.source_columns.items()
    }

    validate_source_cursor_input_columns(
        model=model,
        cursor_column=test_case.cursor_column,
        models_by_name=build_cursor_input_contract_models(test_case),
        source_map=build_cursor_input_contract_sources(test_case),
        source_warehouse_columns=source_warehouse_columns,
    )

    assert test_case.expected_valid is True


@pytest.mark.parametrize(
    "test_case",
    CURSOR_INPUT_ERROR_TEST_CASES,
    ids=[case.description for case in CURSOR_INPUT_ERROR_TEST_CASES],
)
def test_given_missing_cursor_input_source_column_when_validating_then_raises_clear_error(
    test_case: SourceCursorInputColumnsTestCase,
) -> None:
    model: CompiledModel = build_source_cursor_input_model(test_case)
    source_warehouse_columns: dict[str, tuple[ColumnInfo, ...]] = {
        source_name: tuple(ColumnInfo(name=name, type="") for name in column_names)
        for source_name, column_names in test_case.source_columns.items()
    }
    assert test_case.expected_error_fragment is not None

    with pytest.raises(PlannerInputError, match=test_case.expected_error_fragment):
        validate_source_cursor_input_columns(
            model=model,
            cursor_column=test_case.cursor_column,
            models_by_name=build_cursor_input_contract_models(test_case),
            source_map=build_cursor_input_contract_sources(test_case),
            source_warehouse_columns=source_warehouse_columns,
        )

    assert test_case.expected_valid is False
