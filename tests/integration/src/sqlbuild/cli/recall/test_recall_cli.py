import json
import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import (
    DeprecatedFormatTestCase,
    JsonErrorTestCase,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import run, write_project

TABLE_DEPRECATION: str = "--format table is deprecated and will be removed"


@pytest.mark.parametrize(
    "test_case",
    [
        JsonErrorTestCase(
            description="an invalid query",
            args=("recall", "query", "--json", "SELECT no_such_column FROM invocations"),
            expected_code="C974",
        ),
        JsonErrorTestCase(
            description="a write statement",
            args=("recall", "query", "--format", "json", "DELETE FROM recall_output"),
            expected_code="C974",
        ),
        JsonErrorTestCase(
            description="a read store with no history",
            args=("recall", "query", "--json", "SELECT 1", "--target", "missing"),
            expected_code="C971",
        ),
        JsonErrorTestCase(
            description="a schema request without a store",
            args=("recall", "schema", "--json", "--target", "missing"),
            expected_code="C971",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_failing_recall_command_with_json_when_run_then_stdout_is_a_json_error(
    test_case: JsonErrorTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(
        tmp_path / "orders_shop",
        extra_toml=(
            '\n[connections.elsewhere]\nadapter = "sqlite"\npath = "missing/history.sqlite3"\n'
            '\n[targets.missing]\nconnection = "local"\nschema = "dev"\n'
            '[targets.missing.recall]\nread_connection = "elsewhere"\n'
        ),
    )
    assert run(project_dir, "build").returncode == 0

    failed: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    document: dict[str, dict[str, object]] = json.loads(failed.stdout)
    assert failed.returncode == 1
    assert document["error"]["code"] == test_case.expected_code
    assert isinstance(document["error"]["message"], str)
    assert f"error[{test_case.expected_code}]" in failed.stderr.decode()


@pytest.mark.parametrize(
    "test_case",
    [
        DeprecatedFormatTestCase(
            description="table still renders and warns",
            args=("recall", "query", "--format", "table", "SELECT 1 AS answer"),
            expected_warning=True,
        ),
        DeprecatedFormatTestCase(
            description="the schema table warns too",
            args=("recall", "schema", "--format", "table"),
            expected_warning=True,
        ),
        DeprecatedFormatTestCase(
            description="the default long format does not warn",
            args=("recall", "query", "SELECT 1 AS answer"),
            expected_warning=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_the_table_format_when_querying_then_it_works_with_a_deprecation_warning(
    test_case: DeprecatedFormatTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    assert run(project_dir, "build").returncode == 0

    rendered: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    assert rendered.returncode == 0
    assert rendered.stdout
    assert (TABLE_DEPRECATION in rendered.stderr.decode()) is test_case.expected_warning
