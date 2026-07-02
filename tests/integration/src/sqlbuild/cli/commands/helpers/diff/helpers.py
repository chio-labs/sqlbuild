from __future__ import annotations

from decimal import Decimal

from sqlbuild.adapter.shared.models import (
    ColumnInfo,
    RowDiffColumnResult,
    RowDiffResult,
    RowDiffSampleCell,
    RowDiffSampleRow,
    RowDiffTolerance,
    SchemaDiffResult,
)
from sqlbuild.cli.commands.helpers.diff.output import render_diff_output
from sqlbuild.executor.diff.models import DiffExecutionResult, ModelDiffResult
from tests.integration.src.sqlbuild.cli.commands.helpers.diff._test_types import (
    DiffOutputIntegrationTestCase,
)


def build_execution_result(*model_results: ModelDiffResult) -> DiffExecutionResult:
    return DiffExecutionResult(model_results=model_results)


def build_model_result(
    *,
    name: str = "orders",
    schema_result: SchemaDiffResult | None = None,
    row_result: RowDiffResult | None = None,
    unique_key: tuple[str, ...] = ("id",),
    unequal_row_samples: tuple[RowDiffSampleRow, ...] = (),
    left_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = (),
    right_only_key_samples: tuple[tuple[tuple[str, object], ...], ...] = (),
    bounded_fallback: bool = False,
    excluded_columns: tuple[str, ...] = (),
) -> ModelDiffResult:
    return ModelDiffResult(
        name=name,
        left_relation=f"prod.{name}",
        right_relation=f"dev.{name}",
        unique_key=unique_key,
        schema_result=schema_result if schema_result is not None else SchemaDiffResult(),
        row_result=row_result,
        unequal_row_samples=unequal_row_samples,
        left_only_key_samples=left_only_key_samples,
        right_only_key_samples=right_only_key_samples,
        bounded_fallback=bounded_fallback,
        excluded_columns=excluded_columns,
    )


def build_row_result(
    *,
    left_count: int = 3,
    right_count: int = 3,
    equal_count: int = 3,
    unequal_count: int = 0,
    left_only_count: int = 0,
    right_only_count: int = 0,
    column_results: tuple[RowDiffColumnResult, ...] = (),
) -> RowDiffResult:
    return RowDiffResult(
        left_count=left_count,
        right_count=right_count,
        joined_count=equal_count + unequal_count,
        equal_count=equal_count,
        unequal_count=unequal_count,
        left_only_count=left_only_count,
        right_only_count=right_only_count,
        column_results=column_results,
    )


def build_column_result(
    *,
    name: str,
    mismatched_count: int,
    absolute_tolerance: str | None = None,
    relative_tolerance: str | None = None,
) -> RowDiffColumnResult:
    tolerance: RowDiffTolerance | None = None
    if absolute_tolerance is not None or relative_tolerance is not None:
        tolerance = RowDiffTolerance(
            absolute=Decimal(absolute_tolerance) if absolute_tolerance is not None else None,
            relative=Decimal(relative_tolerance) if relative_tolerance is not None else None,
        )
    return RowDiffColumnResult(
        name=name,
        mismatched_count=mismatched_count,
        tolerance=tolerance,
    )


def build_sample_row(
    *,
    key: object,
    changed_cells: tuple[RowDiffSampleCell, ...],
) -> RowDiffSampleRow:
    return RowDiffSampleRow(
        key_values=(("id", key),),
        changed_cells=changed_cells,
    )


def build_sample_cell(
    *,
    name: str,
    left_value: object,
    right_value: object,
) -> RowDiffSampleCell:
    return RowDiffSampleCell(
        name=name,
        left_value=left_value,
        right_value=right_value,
    )


def build_schema_result(
    *,
    added_columns: tuple[ColumnInfo, ...] = (),
    removed_columns: tuple[ColumnInfo, ...] = (),
    type_changed_columns: tuple[tuple[ColumnInfo, ColumnInfo], ...] = (),
) -> SchemaDiffResult:
    return SchemaDiffResult(
        added_columns=added_columns,
        removed_columns=removed_columns,
        type_changed_columns=type_changed_columns,
    )


def build_column(name: str, column_type: str) -> ColumnInfo:
    return ColumnInfo(name=name, type=column_type)


def render_test_case(test_case: DiffOutputIntegrationTestCase) -> str:
    return render_diff_output(
        result=test_case.result,
        from_label=test_case.from_label,
        to_label=test_case.to_label,
        mode_label=test_case.mode_label,
        use_color=False,
        verbose=test_case.verbose,
        max_column_examples=test_case.max_column_examples,
        max_row_only_examples=test_case.max_row_only_examples,
    )


def assert_output_fragments(
    *,
    output: str,
    test_case: DiffOutputIntegrationTestCase,
) -> None:
    expected_fragment: str
    for expected_fragment in test_case.expected_fragments:
        assert expected_fragment in output

    unexpected_fragment: str
    for unexpected_fragment in test_case.unexpected_fragments:
        assert unexpected_fragment not in output
