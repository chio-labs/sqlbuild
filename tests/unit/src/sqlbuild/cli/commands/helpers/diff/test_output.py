from __future__ import annotations

from decimal import Decimal

import pytest

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
from tests.unit.src.sqlbuild.cli.commands.helpers.diff._test_types import (
    RenderDiffOutputTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        RenderDiffOutputTestCase(
            description="renders concise diff summary with side names and changed column cap",
            result=DiffExecutionResult(
                model_results=(
                    ModelDiffResult(
                        name="orders_snapshot",
                        left_relation="prod.orders_snapshot",
                        right_relation="dev.orders_snapshot",
                        unique_key=("order_id",),
                        schema_result=SchemaDiffResult(),
                        row_result=RowDiffResult(
                            left_count=10,
                            right_count=11,
                            joined_count=8,
                            equal_count=6,
                            unequal_count=2,
                            left_only_count=2,
                            right_only_count=3,
                            column_results=(
                                RowDiffColumnResult(name="amount_cents", mismatched_count=2),
                                RowDiffColumnResult(name="payment_method", mismatched_count=1),
                                RowDiffColumnResult(name="ordered_at", mismatched_count=1),
                                RowDiffColumnResult(name="customer_id", mismatched_count=1),
                                RowDiffColumnResult(name="waffle_name", mismatched_count=1),
                                RowDiffColumnResult(name="line_total_cents", mismatched_count=1),
                            ),
                        ),
                        unequal_row_samples=(
                            RowDiffSampleRow(
                                key_values=(("order_id", 1),),
                                changed_cells=(
                                    RowDiffSampleCell(
                                        name="amount_cents",
                                        left_value=100,
                                        right_value=105,
                                    ),
                                ),
                            ),
                        ),
                        left_only_key_samples=((("order_id", 11),),),
                        right_only_key_samples=((("order_id", 12),),),
                        excluded_columns=("status",),
                    ),
                )
            ),
            from_label="prod",
            to_label="dev",
            mode_label="full",
            verbose=False,
            max_column_examples=3,
            max_row_only_examples=3,
            expected_fragments=(
                "SQLBuild Diff Summary",
                "prod vs dev",
                "Model",
                "orders_snapshot",
                "order_id",
                "Comparison",
                "No schema differences.",
                "Excluded",
                "status",
                "prod only",
                "dev only",
                "joined",
                "Changed Columns",
                "amount_cents",
                "payment_method",
                "and 1 more",
                "order_id=1 | 100 -> 105",
                "prod only",
                "order_id=11",
            ),
        ),
        RenderDiffOutputTestCase(
            description="renders tolerances and schema-only row skip message",
            result=DiffExecutionResult(
                model_results=(
                    ModelDiffResult(
                        name="customer_totals",
                        left_relation="prod.customer_totals",
                        right_relation="dev.customer_totals",
                        schema_result=SchemaDiffResult(
                            added_columns=(ColumnInfo(name="new_col", type="INTEGER"),),
                        ),
                        row_result=None,
                        bounded_fallback=False,
                        excluded_columns=(),
                    ),
                    ModelDiffResult(
                        name="orders_snapshot",
                        left_relation="prod.orders_snapshot",
                        right_relation="dev.orders_snapshot",
                        unique_key=("order_id",),
                        schema_result=SchemaDiffResult(),
                        row_result=RowDiffResult(
                            left_count=3,
                            right_count=3,
                            joined_count=1,
                            equal_count=1,
                            unequal_count=0,
                            left_only_count=1,
                            right_only_count=1,
                            column_results=(
                                RowDiffColumnResult(
                                    name="amount_cents",
                                    mismatched_count=0,
                                    tolerance=RowDiffTolerance(absolute=Decimal("1")),
                                ),
                            ),
                        ),
                        unequal_row_samples=(
                            RowDiffSampleRow(
                                key_values=(("order_id", 1),),
                                changed_cells=(
                                    RowDiffSampleCell(
                                        name="amount_cents",
                                        left_value=100,
                                        right_value=101,
                                    ),
                                ),
                            ),
                        ),
                        left_only_key_samples=((("order_id", 11),),),
                        right_only_key_samples=((("order_id", 12),),),
                        bounded_fallback=True,
                    ),
                )
            ),
            from_label="prod",
            to_label="dev",
            mode_label="bounded 30d",
            verbose=True,
            max_column_examples=10,
            max_row_only_examples=10,
            expected_fragments=(
                "schema differences: 1",
                "added columns: 1",
                "Comparison",
                "amount_cents absolute=1",
                "Fallback",
                "no cursor configured; used full row diff",
                "No changed columns.",
                "Examples",
                "order_id=1 | 100 -> 101",
                "prod only",
                "order_id=11",
                "dev only",
                "order_id=12",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_diff_execution_result_when_rendering_then_output_matches_expected_sections(
    test_case: RenderDiffOutputTestCase,
) -> None:
    result: str = render_diff_output(
        result=test_case.result,
        from_label=test_case.from_label,
        to_label=test_case.to_label,
        mode_label=test_case.mode_label,
        use_color=False,
        verbose=test_case.verbose,
        max_column_examples=test_case.max_column_examples,
        max_row_only_examples=test_case.max_row_only_examples,
    )

    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result
