from __future__ import annotations

import pytest

from tests.integration.src.sqlbuild.cli.commands.helpers.diff._test_types import (
    DiffOutputIntegrationTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.helpers.diff.helpers import (
    assert_output_fragments,
    build_column,
    build_execution_result,
    build_model_result,
    build_row_result,
    build_schema_result,
    render_test_case,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DiffOutputIntegrationTestCase(
            description="no schema drift renders clean schema message",
            result=build_execution_result(
                build_model_result(
                    schema_result=build_schema_result(),
                    row_result=build_row_result(),
                )
            ),
            mode_label="full",
            expected_fragments=("Schemas", "No schema differences."),
            unexpected_fragments=("schema differences:", "added columns:", "removed columns:"),
        ),
        DiffOutputIntegrationTestCase(
            description="added columns only renders added column count",
            result=build_execution_result(
                build_model_result(
                    schema_result=build_schema_result(
                        added_columns=(build_column("new_amount", "INTEGER"),)
                    ),
                    row_result=None,
                )
            ),
            mode_label="schema-only",
            expected_fragments=("schema differences: 1", "added columns: 1"),
            unexpected_fragments=("removed columns:", "type changes:"),
        ),
        DiffOutputIntegrationTestCase(
            description="removed columns only renders removed column count",
            result=build_execution_result(
                build_model_result(
                    schema_result=build_schema_result(
                        removed_columns=(build_column("old_amount", "INTEGER"),)
                    ),
                    row_result=None,
                )
            ),
            mode_label="schema-only",
            expected_fragments=("schema differences: 1", "removed columns: 1"),
            unexpected_fragments=("added columns:", "type changes:"),
        ),
        DiffOutputIntegrationTestCase(
            description="type changes only renders type change count",
            result=build_execution_result(
                build_model_result(
                    schema_result=build_schema_result(
                        type_changed_columns=(
                            (build_column("amount", "INTEGER"), build_column("amount", "BIGINT")),
                        )
                    ),
                    row_result=None,
                )
            ),
            mode_label="schema-only",
            expected_fragments=("schema differences: 1", "type changes: 1"),
            unexpected_fragments=("added columns:", "removed columns:"),
        ),
        DiffOutputIntegrationTestCase(
            description="mixed schema drift renders all schema drift counts",
            result=build_execution_result(
                build_model_result(
                    schema_result=build_schema_result(
                        added_columns=(build_column("new_amount", "INTEGER"),),
                        removed_columns=(build_column("old_amount", "INTEGER"),),
                        type_changed_columns=(
                            (build_column("amount", "INTEGER"), build_column("amount", "BIGINT")),
                        ),
                    ),
                    row_result=None,
                )
            ),
            mode_label="schema-only",
            expected_fragments=(
                "schema differences: 3",
                "added columns: 1",
                "removed columns: 1",
                "type changes: 1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_schema_diff_result_when_rendering_then_matches_schema_matrix(
    test_case: DiffOutputIntegrationTestCase,
) -> None:
    output: str = render_test_case(test_case)

    assert test_case.expected_fragments
    assert_output_fragments(output=output, test_case=test_case)
