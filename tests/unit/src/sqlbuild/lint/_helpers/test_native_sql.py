"""Unit tests for the native SQL lint process boundary."""

from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.lint._helpers import native_sql
from sqlbuild.lint.exceptions import NativeLintError
from sqlbuild.lint.models import LintBody, LintConfig
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    InvalidNativeSqlResponseTestCase,
    NativeSqlReuseTestCase,
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
                '{"code":"SQBL001","message":"bad","start":99,"end":100}]}'
            ),
            expected_message="invalid code, message, or source span",
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
