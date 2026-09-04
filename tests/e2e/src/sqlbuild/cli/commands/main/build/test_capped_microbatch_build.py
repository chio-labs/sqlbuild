"""DuckDB E2E coverage for capped microbatch dependency graphs."""

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    CappedMicrobatchBuildE2ETestCase,
    CappedMicrobatchScenarioE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    capped_microbatch_project_files,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    prepare_inline_project,
    query_duckdb,
    run_sqb,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CappedMicrobatchBuildE2ETestCase(
            description="cap from start advances deferred prefix without advancing downstream",
            limit_action="cap_from_start",
            expected_first_ids=(1, 2, 3),
            expected_final_ids=(1, 2, 3, 4, 5),
            run_count=3,
        ),
        CappedMicrobatchBuildE2ETestCase(
            description="cap from end materializes only latest suffix",
            limit_action="cap_from_end",
            expected_first_ids=(3, 4, 5),
            expected_final_ids=(3, 4, 5),
            run_count=2,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_external_watermark_and_capped_terminal_model_when_building_then_graph_stays_bounded(
    tmp_path: Path,
    test_case: CappedMicrobatchBuildE2ETestCase,
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="capped_microbatch",
        repo_files=capped_microbatch_project_files(limit_action=test_case.limit_action),
    )
    db_path: Path = project_dir / "regression.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw_events VALUES "
        "(1, '2026-01-01 12:00:00'), (2, '2026-01-02 12:00:00'), "
        "(3, '2026-01-03 12:00:00'), (4, '2026-01-04 12:00:00'), "
        "(5, '2026-01-05 12:00:00')"
    )
    connection.close()

    first_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert first_result.returncode == 0, first_result.stdout + first_result.stderr
    first_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM main.downstream_events ORDER BY id",
    )
    assert tuple(row[0] for row in first_rows) == test_case.expected_first_ids
    for _ in range(test_case.run_count - 1):
        repeated_result: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        assert repeated_result.returncode == 0, repeated_result.stdout + repeated_result.stderr

    final_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM main.downstream_events ORDER BY id",
    )
    assert tuple(row[0] for row in final_rows) == test_case.expected_final_ids


@pytest.mark.parametrize(
    "test_case",
    (CappedMicrobatchScenarioE2ETestCase("project warning precedes cap", 0),),
    ids=lambda case: case.description,
)
def test_given_project_warning_outside_model_cap_when_building_then_safety_warns_before_cap_executes(
    tmp_path: Path, test_case: CappedMicrobatchScenarioE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="project_limit_with_model_cap",
        repo_files=capped_microbatch_project_files(
            limit_action="cap_from_end",
            project_limit='[microbatches.limits]\nmax_batches = 2\naction = "warn"',
        ),
    )
    db_path: Path = project_dir / "regression.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw_events VALUES "
        "(1, '2026-01-01 12:00:00'), (2, '2026-01-02 12:00:00'), "
        "(3, '2026-01-03 12:00:00'), (4, '2026-01-04 12:00:00'), "
        "(5, '2026-01-05 12:00:00')"
    )
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    assert "above the per-model limit of 2 (action=warn)" in result.stdout
    assert "above the per-model limit of 3 (action=cap_from_end)" in result.stdout
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM main.downstream_events ORDER BY id",
    )
    assert tuple(row[0] for row in rows) == (3, 4, 5)


@pytest.mark.parametrize(
    "test_case",
    (CappedMicrobatchScenarioE2ETestCase("CLI limit remains hard", 1),),
    ids=lambda case: case.description,
)
def test_given_cli_hard_limit_over_model_cap_when_building_then_invocation_fails_before_execution(
    tmp_path: Path, test_case: CappedMicrobatchScenarioE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="cli_limit_over_model_cap",
        repo_files=capped_microbatch_project_files(limit_action="cap_from_end"),
    )
    db_path: Path = project_dir / "regression.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw_events VALUES "
        "(1, '2026-01-01 12:00:00'), (2, '2026-01-02 12:00:00'), "
        "(3, '2026-01-03 12:00:00'), (4, '2026-01-04 12:00:00'), "
        "(5, '2026-01-05 12:00:00')"
    )
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--max-microbatches", "2"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert "above the per-model limit of 2 (action=error)" in result.stderr
    connection = duckdb.connect(str(db_path))
    try:
        target_names: set[str] = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert "capped_events" not in target_names
    assert "downstream_events" not in target_names


@pytest.mark.parametrize(
    "test_case",
    (CappedMicrobatchScenarioE2ETestCase("watermark jump preserves gap", 0),),
    ids=lambda case: case.description,
)
def test_given_cap_from_end_watermark_jump_when_rebuilding_then_downstream_skips_disjoint_gap(
    tmp_path: Path, test_case: CappedMicrobatchScenarioE2ETestCase
) -> None:
    project_files: dict[str, str] = capped_microbatch_project_files(limit_action="cap_from_end")
    project_files["models/capped_events.sql"] = project_files["models/capped_events.sql"].replace(
        "cursor_end '2026-01-06'", "cursor_end '2026-01-12'"
    )
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="cap_from_end_watermark_jump",
        repo_files=project_files,
    )
    db_path: Path = project_dir / "regression.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw_events VALUES "
        "(1, '2026-01-01 12:00:00'), (2, '2026-01-02 12:00:00'), "
        "(3, '2026-01-03 12:00:00'), (4, '2026-01-04 12:00:00'), "
        "(5, '2026-01-05 12:00:00')"
    )
    connection.close()

    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr

    connection = duckdb.connect(str(db_path))
    connection.execute(
        "INSERT INTO raw_events VALUES "
        "(9, '2026-01-09 12:00:00'), (10, '2026-01-10 12:00:00'), "
        "(11, '2026-01-11 12:00:00')"
    )
    connection.close()
    jumped: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert jumped.returncode == test_case.expected_exit_code, jumped.stdout + jumped.stderr

    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM main.downstream_events ORDER BY id",
    )
    assert tuple(row[0] for row in rows) == (3, 4, 5, 9, 10, 11)
    gap_completions: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT partition_start, partition_end FROM main._sqlbuild_microbatches "
            "WHERE model_name = 'downstream_events' "
            "AND record_type = 'partition_completion' "
            "AND partition_start >= '2026-01-06T00:00:00' "
            "AND partition_end <= '2026-01-09T00:00:00'"
        ),
    )
    assert gap_completions == []


@pytest.mark.parametrize(
    "test_case",
    (CappedMicrobatchScenarioE2ETestCase("bounded any uses uncapped input", 0),),
    ids=lambda case: case.description,
)
def test_given_any_watermarks_and_consumer_end_when_capped_winner_is_later_then_uncapped_input_runs(
    tmp_path: Path, test_case: CappedMicrobatchScenarioE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="capped_any_cursor_end",
        repo_files={
            "sqlbuild_project.toml": dedent(
                """
                name = "capped_any_cursor_end"
                adapter = "duckdb"

                [connection]
                database = "regression.duckdb"
                """
            ).strip()
            + "\n",
            "sources/raw.yml": dedent(
                """
                sources:
                  - name: raw_late
                    schema: main
                    table: raw_late
                  - name: raw_early
                    schema: main
                    table: raw_early
                """
            ).strip()
            + "\n",
            "models/capped_late.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  incremental_mode microbatch,
                  microbatch_strategy watermark,
                  cursor event_time,
                  cursor_type timestamp,
                  cursor_grain day,
                  cursor_start '2026-01-18',
                  cursor_end '2026-01-25',
                  cursor_watermark_mode all,
                  cursor_inputs (
                    raw_late (column event_time, roles [filter, watermark]),
                  ),
                  batch_size 1d,
                  lookback 1d,
                  microbatch_limit (
                    max_batches 3,
                    action cap_from_end,
                  ),
                );
                SELECT id, event_time FROM __source("raw_late")
                """
            ).strip()
            + "\n",
            "models/uncapped_early.sql": dedent(
                """
                MODEL (materialized table);
                SELECT id, event_time FROM __source("raw_early")
                """
            ).strip()
            + "\n",
            "models/any_consumer.sql": dedent(
                """
                MODEL (
                  materialized incremental,
                  incremental_strategy delete_insert,
                  incremental_mode microbatch,
                  microbatch_strategy watermark,
                  cursor event_time,
                  cursor_type timestamp,
                  cursor_grain day,
                  cursor_start '2026-01-01',
                  cursor_end '2026-01-15',
                  cursor_watermark_mode any,
                  cursor_inputs (
                    capped_late (column event_time, roles [filter, watermark]),
                    uncapped_early (column event_time, roles [filter, watermark]),
                  ),
                  batch_size 1d,
                  lookback 1d,
                );
                SELECT id, event_time FROM __ref("capped_late")
                UNION ALL
                SELECT id, event_time FROM __ref("uncapped_early")
                """
            ).strip()
            + "\n",
        },
    )
    db_path: Path = project_dir / "regression.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE raw_late (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw_late VALUES "
        "(18, '2026-01-18 12:00:00'), (19, '2026-01-19 12:00:00'), "
        "(20, '2026-01-20 12:00:00')"
    )
    connection.execute("CREATE TABLE raw_early (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO raw_early VALUES (101, '2026-01-01 12:00:00'), (102, '2026-01-14 12:00:00')"
    )
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert result.returncode == test_case.expected_exit_code, result.stdout + result.stderr
    rows: list[tuple[object, ...]] = query_duckdb(
        db_path=db_path,
        sql="SELECT id FROM main.any_consumer ORDER BY id",
    )
    assert tuple(row[0] for row in rows) == (101, 102)


@pytest.mark.parametrize(
    "test_case",
    (CappedMicrobatchScenarioE2ETestCase("missing history fails closed", 1),),
    ids=lambda case: case.description,
)
def test_given_capped_producer_without_completion_history_when_building_consumer_then_fails_closed(
    tmp_path: Path, test_case: CappedMicrobatchScenarioE2ETestCase
) -> None:
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="missing_capped_history",
        repo_files=capped_microbatch_project_files(limit_action="cap_from_end"),
    )
    db_path: Path = project_dir / "regression.duckdb"

    import duckdb

    connection: duckdb.DuckDBPyConnection = duckdb.connect(str(db_path))
    connection.execute("CREATE TABLE raw_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute("CREATE TABLE capped_events (id INTEGER, event_time TIMESTAMP)")
    connection.execute(
        "INSERT INTO capped_events VALUES (4, '2026-01-04 12:00:00'), (5, '2026-01-05 12:00:00')"
    )
    connection.close()

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "downstream_events"),
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    assert "capped producer completion history is unavailable" in result.stdout + result.stderr
    connection = duckdb.connect(str(db_path))
    try:
        target_names: set[str] = {
            row[0]
            for row in connection.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        connection.close()
    assert "downstream_events" not in target_names


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
