from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.helpers.diff._test_types import (
    DiffOutputIntegrationTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.helpers.diff.helpers import (
    assert_output_fragments,
    build_column_result,
    build_execution_result,
    build_model_result,
    build_row_result,
    render_test_case,
)

TEST_CASES: list[DiffOutputIntegrationTestCase] = [
    DiffOutputIntegrationTestCase(
        description="no selected models renders empty selection message",
        result=build_execution_result(),
        mode_label="full",
        expected_fragments=("No models selected for diff.",),
        unexpected_fragments=("SQLBuild Diff Summary",),
    ),
    DiffOutputIntegrationTestCase(
        description="one clean model renders no change sections",
        result=build_execution_result(
            build_model_result(
                name="orders",
                row_result=build_row_result(),
            )
        ),
        mode_label="full",
        expected_fragments=(
            "SQLBuild Diff Summary",
            "selected models: 1",
            "Model",
            "orders",
            "No schema differences.",
            "joined: 3",
            "No changed columns.",
        ),
        unexpected_fragments=("Fallback", "and 1 more"),
    ),
    DiffOutputIntegrationTestCase(
        description="many changed models render global count and divider",
        result=build_execution_result(
            build_model_result(
                name="orders",
                row_result=build_row_result(
                    equal_count=1,
                    unequal_count=2,
                    column_results=(build_column_result(name="amount", mismatched_count=2),),
                ),
            ),
            build_model_result(
                name="customers",
                row_result=build_row_result(
                    equal_count=2,
                    unequal_count=1,
                    column_results=(build_column_result(name="status", mismatched_count=1),),
                ),
            ),
        ),
        mode_label="full",
        expected_fragments=(
            "selected models: 2",
            "orders",
            "customers",
            "amount",
            "status",
            "unequal",
            "─",
        ),
    ),
    DiffOutputIntegrationTestCase(
        description="schema-only mode renders schema section without row sections",
        result=build_execution_result(
            build_model_result(
                name="schema_only_orders",
                row_result=None,
            )
        ),
        mode_label="schema-only",
        expected_fragments=(
            "schema_only_orders",
            "Comparison",
            "schema-only",
            "No schema differences.",
        ),
        unexpected_fragments=("Rows", "Changed Columns", "joined:"),
    ),
    DiffOutputIntegrationTestCase(
        description="bounded fallback renders fallback metadata",
        result=build_execution_result(
            build_model_result(
                name="bounded_orders",
                row_result=build_row_result(),
                bounded_fallback=True,
            )
        ),
        mode_label="bounded 7d",
        expected_fragments=(
            "bounded_orders",
            "bounded 7d (fallback to full row diff)",
            "Fallback",
            "no cursor configured; used full row diff",
        ),
    ),
    DiffOutputIntegrationTestCase(
        description="side-only samples render actual side names",
        result=build_execution_result(
            build_model_result(
                name="side_only_orders",
                row_result=build_row_result(
                    left_count=4,
                    right_count=4,
                    equal_count=2,
                    left_only_count=1,
                    right_only_count=1,
                ),
                left_only_key_samples=((("id", 10),),),
                right_only_key_samples=((("id", 11),),),
            )
        ),
        mode_label="full",
        expected_fragments=(
            "prod only",
            "dev only",
            "id=10",
            "id=11",
        ),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_diff_result_when_rendering_output_then_matches_output_matrix(
    test_case: DiffOutputIntegrationTestCase,
) -> None:
    output: str = render_test_case(test_case)

    assert test_case.expected_fragments
    assert_output_fragments(output=output, test_case=test_case)
