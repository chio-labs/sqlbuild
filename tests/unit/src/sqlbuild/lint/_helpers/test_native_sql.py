"""Unit tests for the native SQL lint process boundary."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from sqlbuild.compiler.compile.models import ExpansionSpan
from sqlbuild.lint._helpers import native_sql
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import LintBody, LintConfig, LintViolation
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    GeneratedRangeFallbackTestCase,
    InvalidNativeSqlResponseTestCase,
    NativeParseIsolationTestCase,
    NativeSqlFindingTestCase,
    NativeSqlFixTestCase,
    NativeSqlReuseTestCase,
    ReservedCteLintTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        InvalidNativeSqlResponseTestCase(
            description="response must be an object",
            response="[]",
            expected_message="non-object response",
        ),
        InvalidNativeSqlResponseTestCase(
            description="response version must match",
            response='{"version":2,"diagnostics":[]}',
            expected_message="unsupported response version",
        ),
        InvalidNativeSqlResponseTestCase(
            description="diagnostics must be a list",
            response='{"version":1,"diagnostics":{}}',
            expected_message="missing a diagnostics list",
        ),
        InvalidNativeSqlResponseTestCase(
            description="source span must fit SQL text",
            response=(
                '{"version":1,"diagnostics":['
                '{"code":"SQBRSQL001","message":"bad","start":99,"end":100}]}'
            ),
            expected_message="invalid code, message, or source span",
        ),
        InvalidNativeSqlResponseTestCase(
            description="remediation must be present",
            response=(
                '{"version":1,"diagnostics":[{"code":"SQBRSQL001","message":"bad","start":0,"end":1}]}'
            ),
            expected_message="invalid code, message, or source span",
        ),
        InvalidNativeSqlResponseTestCase(
            description="fix edit must have a valid authored range",
            response=(
                '{"version":1,"diagnostics":[{"code":"SQBRSQL001","message":"bad",'
                '"remediation":"repair","start":0,"end":1,'
                '"fix":{"start":1,"end":1,"replacement":"IS"}}]}'
            ),
            expected_message="invalid fix edit",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_invalid_native_response_when_linting_then_boundary_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    test_case: InvalidNativeSqlResponseTestCase,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        native_sql._native,
        "lint_sql_json",
        lambda _request: test_case.response,
    )
    target: Path = tmp_path / "model.sql"
    body: LintBody = LintBody(
        file_path=target,
        body_start=0,
        body_end=8,
        lint_text="SELECT 1",
        passes=(),
    )

    with pytest.raises(NativeLintError, match=test_case.expected_message):
        _ = native_sql.run_native_sql_lint(
            bodies=(body,),
            contents_by_path={target: "SELECT 1"},
            config=LintConfig(dialect="duckdb"),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        NativeParseIsolationTestCase(
            description="one unsupported body",
            error_message="Parse error at line 2, column 8: unsupported GROUPING SETS",
            expected_position=(2, 8),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_one_unparseable_body_when_linting_then_other_files_still_complete(
    test_case: NativeParseIsolationTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    lint_response: Mock = Mock(
        side_effect=[ValueError(test_case.error_message), '{"version":1,"diagnostics":[]}']
    )
    monkeypatch.setattr(native_sql._native, "lint_sql_json", lint_response)
    monkeypatch.setattr(native_sql, "_MAX_NATIVE_LINT_WORKERS", 1)
    failed_path: Path = tmp_path / "failed.sql"
    healthy_path: Path = tmp_path / "healthy.sql"
    failed_text: str = "SELECT category\nGROUP BY GROUPING SETS ((category))"
    healthy_text: str = "SELECT 1"
    bodies: tuple[LintBody, ...] = (
        LintBody(
            file_path=failed_path,
            body_start=0,
            body_end=len(failed_text),
            lint_text=failed_text,
            passes=(),
        ),
        LintBody(
            file_path=healthy_path,
            body_start=0,
            body_end=len(healthy_text),
            lint_text=healthy_text,
            passes=(),
        ),
    )

    result: dict[Path, tuple[LintViolation, ...]] = native_sql.run_native_sql_lint(
        bodies=bodies,
        contents_by_path={failed_path: failed_text, healthy_path: healthy_text},
        config=LintConfig(dialect="snowflake"),
    )

    assert tuple(result) == (failed_path,)
    assert result[failed_path][0].code == "L003"
    assert (result[failed_path][0].line, result[failed_path][0].column) == (
        test_case.expected_position
    )
    assert result[failed_path][0].fix is None


@pytest.mark.parametrize(
    "test_case",
    [NativeSqlReuseTestCase(description="identical expanded SQL bodies", expected_call_count=1)],
    ids=lambda case: case.description,
)
def test_given_identical_expanded_bodies_when_linting_then_native_analysis_is_reused(
    test_case: NativeSqlReuseTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _ = test_case
    calls: list[str] = []

    def lint_sql_json(request: str) -> str:
        calls.append(request)
        return '{"version":1,"diagnostics":[]}'

    monkeypatch.setattr(native_sql._native, "lint_sql_json", lint_sql_json)
    paths: tuple[Path, Path] = (tmp_path / "first.sql", tmp_path / "second.sql")
    bodies: tuple[LintBody, ...] = tuple(
        LintBody(
            file_path=path,
            body_start=0,
            body_end=8,
            lint_text="SELECT 1",
            passes=(),
        )
        for path in paths
    )

    result: dict[Path, tuple] = native_sql.run_native_sql_lint(
        bodies=bodies,
        contents_by_path={path: "SELECT 1" for path in paths},
        config=LintConfig(dialect="duckdb"),
    )

    assert result == {}
    assert len(calls) == test_case.expected_call_count


@pytest.mark.parametrize(
    "test_case",
    [
        ReservedCteLintTestCase(
            description="SQLBuild harness CTE is excluded from generic unused-CTE lint",
            sql="WITH __expected__items AS (SELECT 1) SELECT 1",
            expected_violation_count=0,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_reserved_harness_cte_when_linting_then_framework_input_is_not_reported(
    test_case: ReservedCteLintTestCase,
    tmp_path: Path,
) -> None:
    target: Path = tmp_path / "test.sql"
    body: LintBody = LintBody(
        file_path=target,
        body_start=0,
        body_end=len(test_case.sql),
        lint_text=test_case.sql,
        passes=(),
    )

    result: dict[Path, tuple[LintViolation, ...]] = native_sql.run_native_sql_lint(
        bodies=(body,),
        contents_by_path={target: test_case.sql},
        config=LintConfig(dialect="duckdb"),
    )

    assert sum(len(entries) for entries in result.values()) == test_case.expected_violation_count


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSqlFixTestCase(
            description="multi-branch boolean case has no unsafe partial fix",
            sql=(
                "SELECT CASE "
                "WHEN status = 'open' THEN TRUE "
                "WHEN priority = 'high' THEN TRUE "
                "ELSE FALSE END AS actionable "
                "FROM support_tickets"
            ),
            expected_code="SQBRSQL030",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_multi_branch_boolean_case_when_linting_then_partial_fix_is_withheld(
    test_case: NativeSqlFixTestCase,
    tmp_path: Path,
) -> None:
    target: Path = tmp_path / "support_tickets.sql"
    body: LintBody = LintBody(
        file_path=target,
        body_start=0,
        body_end=len(test_case.sql),
        lint_text=test_case.sql,
        passes=(),
    )

    result: dict[Path, tuple[LintViolation, ...]] = native_sql.run_native_sql_lint(
        bodies=(body,),
        contents_by_path={target: test_case.sql},
        config=LintConfig(
            dialect="duckdb",
            enabled_native_rules=(test_case.expected_code,),
        ),
    )

    assert len(result[target]) == 1
    violation: LintViolation = result[target][0]
    assert violation.code == test_case.expected_code
    assert violation.fix is None


@pytest.mark.parametrize(
    "test_case",
    [
        NativeSqlFindingTestCase(
            description="cross joined relation used by filter is not reported as unused",
            sql=(
                "SELECT orders.order_id "
                "FROM orders "
                "CROSS JOIN processing_cutoff AS cutoff "
                "WHERE orders.created_at < cutoff.created_at"
            ),
            selected_rule="SQBRSQL032",
            expected_violation_count=0,
        ),
        NativeSqlFindingTestCase(
            description="lateral relation used by parenthesized later join is not reported",
            sql=(
                "SELECT orders.order_id, products.name "
                "FROM orders "
                "CROSS JOIN LATERAL UNNEST(orders.product_ids) AS item "
                "INNER JOIN products ON (products.product_id = item.product_id)"
            ),
            selected_rule="SQBRSQL032",
            expected_violation_count=0,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cross_join_used_downstream_when_linting_then_no_unused_join_is_reported(
    test_case: NativeSqlFindingTestCase,
    tmp_path: Path,
) -> None:
    target: Path = tmp_path / "orders.sql"
    body: LintBody = LintBody(
        file_path=target,
        body_start=0,
        body_end=len(test_case.sql),
        lint_text=test_case.sql,
        passes=(),
    )

    result: dict[Path, tuple[LintViolation, ...]] = native_sql.run_native_sql_lint(
        bodies=(body,),
        contents_by_path={target: test_case.sql},
        config=LintConfig(
            dialect="duckdb",
            enabled_native_rules=(test_case.selected_rule,),
        ),
    )

    assert sum(len(violations) for violations in result.values()) == (
        test_case.expected_violation_count
    )


@pytest.mark.parametrize(
    "test_case",
    [
        GeneratedRangeFallbackTestCase(
            description="diagnostic crossing one macro expansion",
            authored="SELECT a@macro()b",
            expanded="SELECT aLIMITb",
            diagnostic_start=7,
            diagnostic_end=14,
            expected_position=(1, 8),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_diagnostic_crossing_generated_sql_when_mapping_then_range_falls_back_to_point(
    test_case: GeneratedRangeFallbackTestCase,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Do not fabricate an authored range when a native span crosses an expansion."""

    response: str = json.dumps(
        {
            "version": 1,
            "diagnostics": [
                {
                    "code": "SQBRSQL004",
                    "message": "bad",
                    "remediation": "fix it",
                    "start": test_case.diagnostic_start,
                    "end": test_case.diagnostic_end,
                }
            ],
        }
    )
    monkeypatch.setattr(native_sql._native, "lint_sql_json", lambda _request: response)
    target: Path = tmp_path / "model.sql"
    body: LintBody = LintBody(
        file_path=target,
        body_start=0,
        body_end=len(test_case.authored),
        lint_text=test_case.expanded,
        passes=(
            (
                ExpansionSpan(
                    source_start=8,
                    source_end=16,
                    output_start=8,
                    output_end=13,
                ),
            ),
        ),
    )

    result: dict[Path, tuple[LintViolation, ...]] = native_sql.run_native_sql_lint(
        bodies=(body,),
        contents_by_path={target: test_case.authored},
        config=LintConfig(dialect="duckdb"),
    )

    violation: LintViolation = result[target][0]
    assert (violation.line, violation.column) == test_case.expected_position
    assert (violation.end_line, violation.end_column) == (None, None)
