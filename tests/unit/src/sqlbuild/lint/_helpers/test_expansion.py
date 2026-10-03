"""Lint bodies are prepared natively in one batch with per-body results and failure order."""

from __future__ import annotations

from pathlib import Path

import pytest

import sqlbuild._native as native_module
from sqlbuild.lint.exceptions import ProjectCompileError
from sqlbuild.lint.main.run_lint import run_lint
from sqlbuild.lint.models import LintConfig, LintRunResult
from tests.unit.src.sqlbuild.lint._helpers._test_types import (
    BatchedPreparationFailureTestCase,
    BatchedPreparationTestCase,
)
from tests.unit.src.sqlbuild.lint._helpers.helpers import (
    prepare_nothing_in_batch,
    refuse_preparation,
    write_lint_project,
)

_ORDERS_MODEL: str = (
    'MODEL (description "Orders");\n'
    'SELECT o.customer_id FROM __ref("customers") AS o WHERE o.region = NULL\n'
)
_CUSTOMERS_MODEL: str = (
    "MODEL (description \"Customers\");\nSELECT 1 AS customer_id, 'west' AS region\n"
)
_ORDERS_TEST: str = (
    "TEST ();\nWITH\n__ref__customers AS (SELECT 1 AS customer_id, 'west' AS region),\n"
    "__expected__orders AS (SELECT 1 AS customer_id)\nSELECT 1\n"
)
_NOT_NULL_AUDIT: str = "AUDIT ();\nSELECT 1 FROM @relation WHERE @column IS NULL\n"


@pytest.mark.parametrize(
    "test_case",
    [
        BatchedPreparationTestCase(
            description="models, tests, and generic audits",
            files={
                "models/customers.sql": _CUSTOMERS_MODEL,
                "models/orders.sql": _ORDERS_MODEL,
                "tests/unit/test_orders.sql": _ORDERS_TEST,
                "audits/generic/not_null.sql": _NOT_NULL_AUDIT,
            },
            expected_codes=("SQBRSQL001",),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_linting_with_batched_preparation_then_result_matches_per_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: BatchedPreparationTestCase
) -> None:
    write_lint_project(root=tmp_path, files=test_case.files)
    config: LintConfig = LintConfig(dialect="duckdb")

    batched: LintRunResult = run_lint(project_dir=tmp_path, config=config)
    monkeypatch.setattr(native_module, "prepare_lint_sql_batch", prepare_nothing_in_batch)
    per_body: LintRunResult = run_lint(project_dir=tmp_path, config=config)

    assert batched == per_body
    assert tuple(violation.code for violation in batched.violations) == test_case.expected_codes


@pytest.mark.parametrize(
    "test_case",
    [
        BatchedPreparationFailureTestCase(
            description="native failure before a later unexpandable file",
            unexpandable_file="models/zz_broken.sql",
            skip_unexpandable=False,
            expected_error=ValueError,
        ),
        BatchedPreparationFailureTestCase(
            description="unexpandable file before a later native failure",
            unexpandable_file="models/aa_broken.sql",
            skip_unexpandable=False,
            expected_error=ProjectCompileError,
        ),
        BatchedPreparationFailureTestCase(
            description="skipped unexpandable file before a later native failure",
            unexpandable_file="models/aa_broken.sql",
            skip_unexpandable=True,
            expected_error=ValueError,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_native_and_expansion_failures_when_linting_then_first_in_file_order_is_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, test_case: BatchedPreparationFailureTestCase
) -> None:
    write_lint_project(
        root=tmp_path,
        files={
            "models/customers.sql": _CUSTOMERS_MODEL,
            "models/orders.sql": _ORDERS_MODEL,
            test_case.unexpandable_file: 'MODEL (description "Broken");\nSELECT @unknown()\n',
        },
    )
    monkeypatch.setattr(native_module, "prepare_lint_sql_batch", prepare_nothing_in_batch)
    monkeypatch.setattr(native_module, "prepare_lint_sql", refuse_preparation)

    with pytest.raises(Exception) as raised:
        _ = run_lint(
            project_dir=tmp_path,
            config=LintConfig(dialect="duckdb"),
            skip_unexpandable=test_case.skip_unexpandable,
        )

    assert type(raised.value) is test_case.expected_error


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-n", "auto", "--dist", "loadfile"]))
