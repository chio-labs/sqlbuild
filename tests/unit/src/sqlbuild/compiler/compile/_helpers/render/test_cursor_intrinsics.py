from __future__ import annotations

import pytest

from sqlbuild.compiler.compile._helpers.analysis.columns import infer_columns_with_sql_analysis
from sqlbuild.compiler.compile._helpers.render.cursor_intrinsics import (
    cursor_intrinsics_analysis_sql,
    get_validated_model_cursor_intrinsics,
    reject_cursor_intrinsics,
    render_cursor_intrinsics,
)
from sqlbuild.compiler.compile.exceptions import CompileInputError
from sqlbuild.compiler.compile.models import InferredColumn
from sqlbuild.compiler.lineage.types import InferredNullability
from tests.unit.src.sqlbuild.compiler.compile._helpers.render._test_types import (
    CursorIntrinsicAnalysisTestCase,
    CursorIntrinsicErrorTestCase,
    CursorIntrinsicRenderTestCase,
    CursorIntrinsicValidationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIntrinsicValidationTestCase(
            description="canonicalizes valid incremental intrinsics",
            sql="SELECT __cursor_start  ( ), __cursor_end()",
            expected_sql="SELECT __cursor_start(), __cursor_end()",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_valid_incremental_query_when_validating_then_canonicalizes_intrinsics(
    test_case: CursorIntrinsicValidationTestCase,
) -> None:
    sql: str = get_validated_model_cursor_intrinsics(
        sql=test_case.sql,
        config_values={"materialized": "incremental", "cursor": "event_time"},
        model_name="events",
    )

    assert sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIntrinsicRenderTestCase(
            description="ignores calls in comments and literals",
            sql=(
                "SELECT '__cursor_start()', __cursor_start() AS bound "
                "-- __cursor_end()\n/* __cursor_start() */"
            ),
            expected_sql=(
                "SELECT '__cursor_start()', TIMESTAMP '2026-01-01' AS bound "
                "-- __cursor_end()\n/* __cursor_start() */"
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_comments_and_literals_when_rendering_then_only_replaces_executable_calls(
    test_case: CursorIntrinsicRenderTestCase,
) -> None:
    sql: str = render_cursor_intrinsics(
        sql=test_case.sql,
        start_sql="TIMESTAMP '2026-01-01'",
        end_sql="TIMESTAMP '2026-01-02'",
    )

    assert sql == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIntrinsicErrorTestCase(
            description="rejects arguments",
            sql="SELECT __cursor_start(1)",
            expected_error_fragment="does not accept arguments",
        ),
        CursorIntrinsicErrorTestCase(
            description="rejects missing call suffix",
            sql="SELECT __cursor_end",
            expected_error_fragment="must be called with",
        ),
        CursorIntrinsicErrorTestCase(
            description="rejects reserved executor marker",
            sql="SELECT '__SQB_CURSOR_START__'",
            expected_error_fragment="reserved internal cursor marker",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_intrinsic_when_validating_then_raises(
    test_case: CursorIntrinsicErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        get_validated_model_cursor_intrinsics(
            sql=test_case.sql,
            config_values={"materialized": "incremental", "cursor": "event_time"},
            model_name="events",
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIntrinsicErrorTestCase(
            description="rejects an audit intrinsic",
            sql="SELECT __cursor_start()",
            expected_error_fragment="only supported",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_unsupported_sql_context_when_rejecting_then_raises(
    test_case: CursorIntrinsicErrorTestCase,
) -> None:
    with pytest.raises(CompileInputError, match=test_case.expected_error_fragment):
        reject_cursor_intrinsics(sql=test_case.sql, context="Audit 'freshness'")


@pytest.mark.parametrize(
    "test_case",
    [
        CursorIntrinsicAnalysisTestCase(
            description="timestamp bound",
            cursor_type="timestamp",
            expected_type="TIMESTAMP",
        ),
        CursorIntrinsicAnalysisTestCase(
            description="integer bound",
            cursor_type="integer",
            expected_type="BIGINT",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_typed_intrinsic_when_analyzing_then_infers_non_null_column(
    test_case: CursorIntrinsicAnalysisTestCase,
) -> None:
    analysis_sql: str = cursor_intrinsics_analysis_sql(
        sql="SELECT __cursor_start() AS batch_start",
        cursor_type=test_case.cursor_type,
    )

    assert infer_columns_with_sql_analysis(query_sql=analysis_sql) == (
        InferredColumn(
            name="batch_start",
            type=test_case.expected_type,
            nullability=InferredNullability.NON_NULL,
        ),
    )
