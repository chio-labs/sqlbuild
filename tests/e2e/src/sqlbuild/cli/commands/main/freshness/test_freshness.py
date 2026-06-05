from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.freshness._test_types import (
    FreshnessE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.freshness.helpers import prepare_freshness_project
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessE2ETestCase(
            description="observes configured source freshness without writing state",
            expected_fragments=(
                "Source freshness",
                "Observed (1)",
                "raw_orders  integer  1  sql",
                "Summary: observed=1 unknown=0 errors=0",
            ),
        )
    ],
    ids=["observes configured source freshness without writing state"],
)
def test_given_configured_source_freshness_when_running_then_observes_read_only(
    test_case: FreshnessE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_freshness_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "freshness", "--select", "raw_orders"),
        project_dir=project_dir,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    assert not table_exists(
        db_path=project_dir / "warehouse.duckdb",
        table_name="_sqlbuild_source_freshness",
    )

    json_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("freshness", "--select", "raw_orders", "--json"),
        project_dir=project_dir,
    )
    payload: dict[str, Any] = json.loads(json_result.stdout)
    assert json_result.returncode == 0, json_result.stdout + json_result.stderr
    assert payload["summary"] == {"observed": 1, "unknown": 0, "errors": 0}
    assert payload["sources"][0]["name"] == "raw_orders"
    assert payload["sources"][0]["status"] == "observed"

    json_output_path: Path = project_dir / "target" / "freshness.json"
    json_file_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "freshness",
            "--select",
            "raw_orders",
            "--json-output",
            str(json_output_path),
        ),
        project_dir=project_dir,
    )
    file_payload: dict[str, Any] = json.loads(json_output_path.read_text(encoding="utf-8"))
    assert json_file_result.returncode == 0, json_file_result.stdout + json_file_result.stderr
    assert "Source freshness" in json_file_result.stdout
    assert file_payload["summary"] == {"observed": 1, "unknown": 0, "errors": 0}


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessE2ETestCase(
            description="fail on error returns nonzero for unknown source freshness",
            expected_fragments=(
                "Unknown (1)",
                "raw_unknown  no freshness config and adapter metadata unavailable",
                "Summary: observed=0 unknown=1 errors=0",
            ),
        )
    ],
    ids=["fail on error returns nonzero for unknown source freshness"],
)
def test_given_unknown_source_freshness_when_fail_on_error_then_returns_nonzero(
    test_case: FreshnessE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_freshness_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "freshness", "--select", "raw_unknown", "--fail-on-error"),
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessE2ETestCase(
            description="explicit freshness error returns nonzero with fail on error",
            expected_fragments=(
                "Errors (1)",
                'raw_error  Binder Error: Referenced column "missing_column"',
                "Summary: observed=0 unknown=0 errors=1",
            ),
        )
    ],
    ids=["explicit freshness error returns nonzero with fail on error"],
)
def test_given_source_freshness_error_when_fail_on_error_then_returns_nonzero(
    test_case: FreshnessE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_freshness_project(tmp_path=tmp_path)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "freshness", "--select", "raw_error", "--fail-on-error"),
        project_dir=project_dir,
    )

    assert result.returncode == 1, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout


@pytest.mark.parametrize(
    "test_case",
    [
        FreshnessE2ETestCase(
            description="existing source freshness state table is not modified",
            expected_fragments=(
                "Observed (1)",
                "Summary: observed=1 unknown=0 errors=0",
            ),
        )
    ],
    ids=["existing source freshness state table is not modified"],
)
def test_given_existing_source_freshness_state_when_running_then_does_not_write_state(
    test_case: FreshnessE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_freshness_project(tmp_path=tmp_path)
    db_path: Path = project_dir / "warehouse.duckdb"
    execute_duckdb(
        db_path=db_path,
        sql=(
            "CREATE TABLE _sqlbuild_source_freshness ("
            "source_name VARCHAR, target_database VARCHAR, target_schema VARCHAR, "
            "target_name VARCHAR, run_id VARCHAR, strategy VARCHAR, value_kind VARCHAR, "
            "data_version VARCHAR, data_version_hash VARCHAR, observed_at TIMESTAMP)"
        ),
    )
    execute_duckdb(
        db_path=db_path,
        sql=(
            "INSERT INTO _sqlbuild_source_freshness VALUES "
            "('raw_orders', NULL, NULL, NULL, 'existing', 'sql', 'integer', "
            "'old', 'old-hash', TIMESTAMP '2026-01-01 00:00:00')"
        ),
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "freshness", "--select", "raw_orders"),
        project_dir=project_dir,
    )

    rows: list[tuple[Any, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT run_id, data_version FROM _sqlbuild_source_freshness",
    )
    assert result.returncode == 0, result.stdout + result.stderr
    fragment: str
    for fragment in test_case.expected_fragments:
        assert fragment in result.stdout, result.stdout
    assert rows == [("existing", "old")]
