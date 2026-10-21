import json
import subprocess
from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.recall._test_types import (
    DeprecatedFormatTestCase,
    JsonErrorTestCase,
    LeanRecallTestCase,
    RecallDiagnosticsTestCase,
    RecallUsageErrorTestCase,
    StatementStartTestCase,
    StoreBeingCreatedTestCase,
)
from tests.integration.src.sqlbuild.cli.recall.helpers import (
    OUTPUT_LOG_SINK,
    drop_store_views,
    recall_rows,
    run,
    write_project,
    write_sinks,
)

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
            description="a plan with an unknown selector",
            args=("plan", "--json", "--select", "no_such_model"),
            expected_code="S007",
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


@pytest.mark.parametrize(
    "test_case",
    [
        LeanRecallTestCase(
            description="query",
            args=("recall", "query", "SELECT count(*) FROM invocations"),
            expected_sink_log=False,
        ),
        LeanRecallTestCase(
            description="schema", args=("recall", "schema"), expected_sink_log=False
        ),
        LeanRecallTestCase(
            description="output", args=("recall", "output", "last"), expected_sink_log=False
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_sinks_when_reading_recall_then_no_sink_runs_and_no_compute_log_is_kept(
    test_case: LeanRecallTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    _ = write_sinks(project_dir, {"output_log": OUTPUT_LOG_SINK})
    assert run(project_dir, "build").returncode == 0
    (project_dir / "output.log").unlink()
    logs_before: set[Path] = set((project_dir / "logs").glob("*/*"))

    read: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    assert read.returncode == 0, read.stderr.decode(errors="replace")
    assert read.stdout
    assert (project_dir / "output.log").exists() is test_case.expected_sink_log
    assert set((project_dir / "logs").glob("*/*")) == logs_before


@pytest.mark.parametrize(
    "test_case",
    [
        StatementStartTestCase(
            description="statements carry their invocation's start time",
            sql=(
                "SELECT COUNT(*) > 0, COUNT(DISTINCT s.invocation_started_at = "
                "i.invocation_started_at) FROM statements s JOIN invocations i "
                "USING (invocation_id) WHERE s.invocation_started_at >= "
                "(SELECT MIN(invocation_started_at) FROM invocations)"
            ),
            expected_rows=[[1, 1]],
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_recorded_statements_when_filtered_by_start_time_then_the_view_exposes_it(
    test_case: StatementStartTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    assert run(project_dir, "build").returncode == 0

    rows: list[list[object]] = recall_rows(project_dir, test_case.sql)

    assert rows == test_case.expected_rows


@pytest.mark.parametrize(
    "test_case",
    [
        StoreBeingCreatedTestCase(
            description="a query before the views exist",
            args=("recall", "query", "SELECT COUNT(*) FROM invocations"),
            expected_error="error[C971]: no Recall history is recorded yet",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_store_whose_views_are_still_being_created_when_queried_then_it_is_not_recorded_yet(
    test_case: StoreBeingCreatedTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    assert run(project_dir, "build").returncode == 0
    drop_store_views(project_dir / "logs" / "recall.sqlite3")

    queried: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    assert queried.returncode == 1
    assert test_case.expected_error in queried.stderr.decode()


@pytest.mark.parametrize(
    "test_case",
    [
        RecallUsageErrorTestCase(
            description="--ddl prints SQL, so it cannot be combined with --json",
            args=("recall", "schema", "--ddl", "--json"),
            expected_message="argument --json: not allowed with argument --ddl",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_conflicting_recall_options_when_parsed_then_it_is_a_usage_error(
    test_case: RecallUsageErrorTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")

    rejected: subprocess.CompletedProcess[bytes] = run(project_dir, *test_case.args)

    assert rejected.returncode == 2
    assert rejected.stdout == b""
    assert test_case.expected_message in rejected.stderr.decode()


@pytest.mark.parametrize(
    "test_case",
    [
        RecallDiagnosticsTestCase(
            description="--debug routes the failure's diagnostics to the console",
            global_args=("--debug",),
            expected_debug_log=True,
        ),
        RecallDiagnosticsTestCase(
            description="without --debug only the coded error is printed",
            global_args=(),
            expected_debug_log=False,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_a_failing_recall_query_when_run_then_diagnostics_follow_the_debug_option(
    test_case: RecallDiagnosticsTestCase, tmp_path: Path
) -> None:
    project_dir: Path = write_project(tmp_path / "orders_shop")
    assert run(project_dir, "build").returncode == 0

    failed: subprocess.CompletedProcess[bytes] = run(
        project_dir, *test_case.global_args, "recall", "query", "SELECT * FROM missing_orders"
    )

    stderr: str = failed.stderr.decode(errors="replace")
    assert failed.returncode == 1
    assert "error[C974]" in stderr
    assert ("[error] cli" in stderr) is test_case.expected_debug_log
    assert ("CliUserError" in stderr) is test_case.expected_debug_log
