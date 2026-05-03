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
        description="absolute tolerance renders when present",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    column_results=(
                        build_column_result(
                            name="amount",
                            mismatched_count=0,
                            absolute_tolerance="1.5",
                        ),
                    )
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("Tolerances", "amount absolute=1.5"),
        unexpected_fragments=("relative=",),
    ),
    DiffOutputIntegrationTestCase(
        description="relative tolerance renders when present",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    column_results=(
                        build_column_result(
                            name="ratio",
                            mismatched_count=0,
                            relative_tolerance="0.01",
                        ),
                    )
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("Tolerances", "ratio relative=0.01"),
        unexpected_fragments=("absolute=",),
    ),
    DiffOutputIntegrationTestCase(
        description="absolute and relative tolerances render together",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    column_results=(
                        build_column_result(
                            name="price",
                            mismatched_count=0,
                            absolute_tolerance="0.5",
                            relative_tolerance="0.02",
                        ),
                    )
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("Tolerances", "price absolute=0.5 relative=0.02"),
    ),
    DiffOutputIntegrationTestCase(
        description="only columns with resolved tolerances are shown",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    column_results=(
                        build_column_result(
                            name="amount",
                            mismatched_count=0,
                            absolute_tolerance="1",
                        ),
                        build_column_result(name="status", mismatched_count=0),
                    )
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("Tolerances", "amount absolute=1"),
        unexpected_fragments=("status absolute", "status relative"),
    ),
    DiffOutputIntegrationTestCase(
        description="tolerance row is hidden when no tolerance is present",
        result=build_execution_result(
            build_model_result(
                row_result=build_row_result(
                    column_results=(build_column_result(name="amount", mismatched_count=0),)
                ),
            )
        ),
        mode_label="full",
        expected_fragments=("No changed columns.",),
        unexpected_fragments=("Tolerances", "absolute=", "relative="),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TEST_CASES,
    ids=[case.description for case in TEST_CASES],
)
def test_given_tolerance_result_when_rendering_then_matches_tolerance_matrix(
    test_case: DiffOutputIntegrationTestCase,
) -> None:
    output: str = render_test_case(test_case)

    assert test_case.expected_fragments
    assert_output_fragments(output=output, test_case=test_case)
