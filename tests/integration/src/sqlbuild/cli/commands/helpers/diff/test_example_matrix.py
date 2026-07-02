from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.cli.commands.helpers.diff._test_types import (
    DiffOutputIntegrationTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.helpers.diff.helpers import (
    assert_output_fragments,
    build_column_result,
    build_execution_result,
    build_model_result,
    build_row_result,
    build_sample_cell,
    build_sample_row,
    render_test_case,
)

TEST_CASES: list[DiffOutputIntegrationTestCase] = [
    DiffOutputIntegrationTestCase(
        description="one changed column renders concise changed-row example",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    equal_count=1,
                    unequal_count=1,
                    column_results=(build_column_result(name="amount", mismatched_count=1),),
                ),
                unequal_row_samples=(
                    build_sample_row(
                        key=1,
                        changed_cells=(
                            build_sample_cell(name="amount", left_value=10, right_value=12),
                        ),
                    ),
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("amount", "id=1 | 10 -> 12"),
    ),
    DiffOutputIntegrationTestCase(
        description="multiple changed columns in one row render separate examples",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    equal_count=1,
                    unequal_count=1,
                    column_results=(
                        build_column_result(name="amount", mismatched_count=1),
                        build_column_result(name="status", mismatched_count=1),
                    ),
                ),
                unequal_row_samples=(
                    build_sample_row(
                        key=2,
                        changed_cells=(
                            build_sample_cell(name="amount", left_value=10, right_value=12),
                            build_sample_cell(name="status", left_value="old", right_value="new"),
                        ),
                    ),
                ),
            )
        ),
        mode_label="full",
        expected_fragments=(
            "amount",
            "status",
            "id=2 | 10 -> 12",
            "id=2 | old -> new",
        ),
    ),
    DiffOutputIntegrationTestCase(
        description="multiple sampled rows per column render truncation notice",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    equal_count=0,
                    unequal_count=2,
                    column_results=(build_column_result(name="amount", mismatched_count=2),),
                ),
                unequal_row_samples=(
                    build_sample_row(
                        key=3,
                        changed_cells=(
                            build_sample_cell(name="amount", left_value=10, right_value=12),
                        ),
                    ),
                    build_sample_row(
                        key=4,
                        changed_cells=(
                            build_sample_cell(name="amount", left_value=20, right_value=24),
                        ),
                    ),
                ),
            )
        ),
        mode_label="full",
        max_column_examples=1,
        expected_fragments=(
            "id=3 | 10 -> 12",
            "showing 1 of 2 examples",
        ),
        unexpected_fragments=("id=4 | 20 -> 24",),
    ),
    DiffOutputIntegrationTestCase(
        description="side-only samples can be absent while changed examples render",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    equal_count=1,
                    unequal_count=1,
                    column_results=(build_column_result(name="amount", mismatched_count=1),),
                ),
                unequal_row_samples=(
                    build_sample_row(
                        key=5,
                        changed_cells=(
                            build_sample_cell(name="amount", left_value=30, right_value=31),
                        ),
                    ),
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("id=5 | 30 -> 31",),
        unexpected_fragments=("id=4", "id=6"),
    ),
    DiffOutputIntegrationTestCase(
        description="side-only samples truncate independently from column examples",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    left_count=4,
                    right_count=4,
                    equal_count=2,
                    left_only_count=2,
                    right_only_count=2,
                ),
                left_only_key_samples=((("id", 6),), (("id", 7),)),
                right_only_key_samples=((("id", 8),), (("id", 9),)),
            )
        ),
        mode_label="full",
        max_row_only_examples=1,
        expected_fragments=(
            "id=6",
            "id=8",
            "showing 1 of 2 prod only rows",
            "showing 1 of 2 dev only rows",
        ),
        unexpected_fragments=("id=7", "id=9"),
    ),
    DiffOutputIntegrationTestCase(
        description="no changed columns renders no changed column message",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    equal_count=2,
                    unequal_count=0,
                    column_results=(build_column_result(name="amount", mismatched_count=0),),
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("No changed columns.",),
        unexpected_fragments=("Use --verbose to show more example row changes.",),
    ),
    DiffOutputIntegrationTestCase(
        description="verbose examples use larger section and truncation notice",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    equal_count=0,
                    unequal_count=2,
                    column_results=(build_column_result(name="status", mismatched_count=2),),
                ),
                unequal_row_samples=(
                    build_sample_row(
                        key=10,
                        changed_cells=(
                            build_sample_cell(name="status", left_value="old", right_value="new"),
                        ),
                    ),
                    build_sample_row(
                        key=11,
                        changed_cells=(
                            build_sample_cell(name="status", left_value="old", right_value="done"),
                        ),
                    ),
                ),
            )
        ),
        mode_label="full",
        verbose=True,
        max_column_examples=1,
        expected_fragments=("Examples", "id=10 | old -> new", "showing 1 of 2 examples"),
        unexpected_fragments=("id=11 | old -> done",),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_diff_result_when_rendering_examples_then_matches_example_matrix(
    test_case: DiffOutputIntegrationTestCase,
) -> None:
    output: str = render_test_case(test_case)

    assert test_case.expected_fragments
    assert_output_fragments(output=output, test_case=test_case)
