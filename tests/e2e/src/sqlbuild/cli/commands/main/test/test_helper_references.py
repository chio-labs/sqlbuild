"""E2E tests for `__ref()` and mock references inside SQL-test helper CTEs."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.test._test_types import (
    HelperReferenceE2ETestCase,
    HelperReferenceErrorE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.test.helpers import (
    build_helper_reference_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_ENGINE_ENV_VAR: str = "SQLBUILD_COMPILER_ENGINE"
_HELPER_ERROR_CODE: str = "P013"


@pytest.mark.parametrize(
    "test_case",
    (
        HelperReferenceE2ETestCase(
            description="helper and assertion read the model on the python engine",
            tests=("helper_and_assertion_read_model",),
            command=("--no-color", "test"),
            engine="python",
            expected_output_fragments=("PASS=1  FAIL=0  TOTAL=1", "assertion doubles_amount"),
        ),
        HelperReferenceE2ETestCase(
            description="only a helper reads the model on the python engine",
            tests=("only_helper_reads_model",),
            command=("--no-color", "test", "--select", "item_totals"),
            engine="python",
            expected_output_fragments=(
                "1 selected",
                "PASS=1  FAIL=0  TOTAL=1",
                "assertion doubles_amount",
            ),
        ),
        HelperReferenceE2ETestCase(
            description="helper reads a helper and a mock on the python engine",
            tests=("helper_reads_helper_and_mock",),
            command=("--no-color", "test"),
            engine="python",
            expected_output_fragments=(
                "PASS=1  FAIL=0  TOTAL=1",
                "assertion doubles_mocked_amount",
            ),
        ),
        HelperReferenceE2ETestCase(
            description="helper reads a helper and a mock without sql analysis on the python engine",
            tests=("helper_reads_helper_and_mock",),
            command=("--no-color", "test", "--no-sql-analysis"),
            engine="python",
            expected_output_fragments=(
                "PASS=1  FAIL=0  TOTAL=1",
                "assertion doubles_mocked_amount",
            ),
        ),
        HelperReferenceE2ETestCase(
            description="helper and assertion read the model on the native engine",
            tests=("helper_and_assertion_read_model",),
            command=("--no-color", "test"),
            engine="native",
            expected_output_fragments=("PASS=1  FAIL=0  TOTAL=1", "assertion doubles_amount"),
        ),
        HelperReferenceE2ETestCase(
            description="only a helper reads the model on the native engine",
            tests=("only_helper_reads_model",),
            command=("--no-color", "test", "--select", "item_totals"),
            engine="native",
            expected_output_fragments=(
                "1 selected",
                "PASS=1  FAIL=0  TOTAL=1",
                "assertion doubles_amount",
            ),
        ),
        HelperReferenceE2ETestCase(
            description="helper reads a helper and a mock on the native engine",
            tests=("helper_reads_helper_and_mock",),
            command=("--no-color", "test"),
            engine="native",
            expected_output_fragments=(
                "PASS=1  FAIL=0  TOTAL=1",
                "assertion doubles_mocked_amount",
            ),
        ),
        HelperReferenceE2ETestCase(
            description="helper reads a helper and a mock without sql analysis on the native engine",
            tests=("helper_reads_helper_and_mock",),
            command=("--no-color", "test", "--no-sql-analysis"),
            engine="native",
            expected_output_fragments=(
                "PASS=1  FAIL=0  TOTAL=1",
                "assertion doubles_mocked_amount",
            ),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_helper_cte_references_when_testing_then_helpers_read_the_tested_models(
    test_case: HelperReferenceE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="helper_reference_project",
        repo_files=build_helper_reference_project_files(tests=test_case.tests),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
        env={_ENGINE_ENV_VAR: test_case.engine},
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == 0, output
    for fragment in test_case.expected_output_fragments:
        assert fragment in output, output


@pytest.mark.parametrize(
    "test_case",
    (
        HelperReferenceErrorE2ETestCase(
            description="helpers reading each other on the python engine",
            test_name="helper_cycle",
            engine="python",
            expected_message=(
                "SQL test CTE 'first_rows' reads itself through 'first_rows' -> "
                "'second_rows' -> 'first_rows', so the test query cannot define its CTEs in "
                "dependency order"
            ),
            expected_line=7,
            expected_column=1,
            expected_help_fragment="shared_rows AS (SELECT ...)",
        ),
        HelperReferenceErrorE2ETestCase(
            description="helper reading an unknown model on the python engine",
            test_name="helper_reads_unknown_model",
            engine="python",
            expected_message=(
                "SQL test helper CTE 'missing_rows' references unknown model 'item_archive'"
            ),
            expected_line=7,
            expected_column=38,
            expected_help_fragment='__ref("<model>")',
        ),
        HelperReferenceErrorE2ETestCase(
            description="mock reading a helper that reads a model on the python engine",
            test_name="mock_reads_referencing_helper",
            engine="python",
            expected_message=(
                "SQL test mock '__ref__items' reads helper CTE 'base_rows', which calls "
                '__ref("item_totals"); mocks and fixtures are defined before the models the '
                "test runs, so the helper cannot be resolved for them"
            ),
            expected_line=7,
            expected_column=35,
            expected_help_fragment='FROM __ref__item_totals rather than FROM __ref("item_totals")',
        ),
        HelperReferenceErrorE2ETestCase(
            description="helpers reading each other on the native engine",
            test_name="helper_cycle",
            engine="native",
            expected_message=(
                "SQL test CTE 'first_rows' reads itself through 'first_rows' -> "
                "'second_rows' -> 'first_rows', so the test query cannot define its CTEs in "
                "dependency order"
            ),
            expected_line=7,
            expected_column=1,
            expected_help_fragment="shared_rows AS (SELECT ...)",
        ),
        HelperReferenceErrorE2ETestCase(
            description="helper reading an unknown model on the native engine",
            test_name="helper_reads_unknown_model",
            engine="native",
            expected_message=(
                "SQL test helper CTE 'missing_rows' references unknown model 'item_archive'"
            ),
            expected_line=7,
            expected_column=38,
            expected_help_fragment='__ref("<model>")',
        ),
        HelperReferenceErrorE2ETestCase(
            description="mock reading a helper that reads a model on the native engine",
            test_name="mock_reads_referencing_helper",
            engine="native",
            expected_message=(
                "SQL test mock '__ref__items' reads helper CTE 'base_rows', which calls "
                '__ref("item_totals"); mocks and fixtures are defined before the models the '
                "test runs, so the helper cannot be resolved for them"
            ),
            expected_line=7,
            expected_column=35,
            expected_help_fragment='FROM __ref__item_totals rather than FROM __ref("item_totals")',
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_unresolvable_helper_references_when_compiling_then_compile_reports_them(
    test_case: HelperReferenceErrorE2ETestCase, tmp_path: Path
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="helper_reference_project",
        repo_files=build_helper_reference_project_files(tests=(test_case.test_name,)),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "compile", "--json"),
        project_dir=project_dir,
        env={_ENGINE_ENV_VAR: test_case.engine},
    )

    output: str = result.stdout + result.stderr
    assert result.returncode == 1, output
    payload: dict[str, Any] = json.loads(result.stdout)
    codes: list[str] = [diagnostic["code"] for diagnostic in payload["diagnostics"]]
    assert codes == [_HELPER_ERROR_CODE], output
    diagnostic: dict[str, Any] = payload["diagnostics"][0]
    assert diagnostic["message"] == test_case.expected_message, output
    assert diagnostic["location"]["path"] == f"tests/unit/test_{test_case.test_name}.sql"
    assert diagnostic["location"]["line"] == test_case.expected_line, output
    assert diagnostic["location"]["column"] == test_case.expected_column, output
    assert test_case.expected_help_fragment in diagnostic["help"], output
