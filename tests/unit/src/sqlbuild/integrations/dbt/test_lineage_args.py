from __future__ import annotations

import pytest

from sqlbuild.integrations.dbt.exceptions import DbtInteropArgumentError
from sqlbuild.integrations.dbt.helpers.lineage_args import parse_dbt_lineage_args
from sqlbuild.integrations.dbt.models import DbtLineageArgs
from sqlbuild.integrations.dbt.types import DbtLineageDirection, DbtLineageOutputFormat
from tests.unit.src.sqlbuild.integrations.dbt._test_types import (
    DbtLineageArgsErrorTestCase,
    DbtLineageArgsTestCase,
)

LINEAGE_ARGS_ERROR_TEST_CASES: tuple[DbtLineageArgsErrorTestCase, ...] = (
    DbtLineageArgsErrorTestCase(
        description="rejects missing target",
        args=("--format", "json"),
        expected_error_fragment="requires a lineage target resource",
        expected_code="C333",
    ),
    DbtLineageArgsErrorTestCase(
        description="rejects multiple targets",
        args=("orders", "customers"),
        expected_error_fragment="exactly one lineage target resource",
        expected_code="C332",
    ),
    DbtLineageArgsErrorTestCase(
        description="rejects invalid format",
        args=("orders", "--format", "yaml"),
        expected_error_fragment="--format must be tree, json, or list",
        expected_code="C334",
    ),
    DbtLineageArgsErrorTestCase(
        description="rejects invalid direction",
        args=("orders", "--direction", "sideways"),
        expected_error_fragment="--direction must be upstream, downstream, or both",
        expected_code="C335",
    ),
    DbtLineageArgsErrorTestCase(
        description="rejects invalid depth",
        args=("orders", "--depth", "nope"),
        expected_error_fragment="--depth must be a non-negative integer or 'all'",
        expected_code="C304",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        DbtLineageArgsTestCase(
            description="parses full lineage arguments",
            args=(
                "downstream_orders",
                "--format",
                "json",
                "--direction",
                "both",
                "--depth",
                "2",
                "--no-sql-validation",
                "--project-dir",
                "dbt_project",
            ),
            expected_target="downstream_orders",
            expected_output_format=DbtLineageOutputFormat.JSON,
            expected_direction=DbtLineageDirection.BOTH,
            expected_depth=2,
            expected_no_sql_validation=True,
            expected_dbt_args=("--project-dir", "dbt_project"),
        )
    ],
    ids=["parses full lineage arguments"],
)
def test_given_lineage_args_when_parsing_then_returns_expected_values(
    test_case: DbtLineageArgsTestCase,
) -> None:
    parsed: DbtLineageArgs = parse_dbt_lineage_args(test_case.args)

    assert parsed.target == test_case.expected_target
    assert parsed.output_format == test_case.expected_output_format
    assert parsed.direction == test_case.expected_direction
    assert parsed.depth == test_case.expected_depth
    assert parsed.no_sql_validation == test_case.expected_no_sql_validation
    assert parsed.dbt_args == test_case.expected_dbt_args


@pytest.mark.parametrize(
    "test_case",
    LINEAGE_ARGS_ERROR_TEST_CASES,
    ids=[case.description for case in LINEAGE_ARGS_ERROR_TEST_CASES],
)
def test_given_invalid_lineage_args_when_parsing_then_raises_clear_error(
    test_case: DbtLineageArgsErrorTestCase,
) -> None:
    with pytest.raises(DbtInteropArgumentError) as exc_info:
        parse_dbt_lineage_args(test_case.args)

    assert test_case.expected_error_fragment in str(exc_info.value)
    assert exc_info.value.code == test_case.expected_code
