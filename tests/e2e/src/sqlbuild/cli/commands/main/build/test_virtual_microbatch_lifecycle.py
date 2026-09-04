"""E2E coverage for virtual microbatch replay, reconciliation, and generations."""

from __future__ import annotations

import subprocess
from pathlib import Path
from textwrap import dedent

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.build._test_types import (
    CappedMicrobatchScenarioE2ETestCase,
    VirtualConcurrentMicrobatchE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.build.helpers import (
    physical_orders_relation,
    prepare_virtual_microbatch_lifecycle_project,
    timestamp_microbatch_model_sql,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import (
    execute_duckdb,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="virtual state loss synthesizes only virtual events",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_history_loss_when_reconciling_then_synthetic_events_stay_in_state_backend(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_microbatch_synthesis",
        model_sql=timestamp_microbatch_model_sql(
            value_expression="payload",
            batch_concurrency=3,
            replay_policy="forward_only",
        ),
    )
    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    execute_duckdb(
        db_path=state_path,
        sql="DELETE FROM sqlbuild_state.microbatch_events",
    )

    reconciled: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr
    assert reconciled.returncode == test_case.expected_exit_code, (
        reconciled.stdout + reconciled.stderr
    )
    assert "fingerprints are unknown" in reconciled.stdout + reconciled.stderr
    assert (
        query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT COUNT(*) FROM sqlbuild_state.microbatch_events "
                "WHERE record_type = 'synthetic_completion' "
                "AND scope_kind = 'virtual_physical' "
                "AND fingerprint_status = 'unknown' AND model_version_hash IS NULL"
            ),
        )[0][0]
        >= test_case.expected_minimum_event_count
    )
    assert query_duckdb(
        db_path=warehouse_path,
        sql=(
            "SELECT COUNT(*) FROM information_schema.tables "
            "WHERE table_name = '_sqlbuild_microbatches'"
        ),
    ) == [(0,)]
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders ORDER BY id",
    ) == [(1, "1"), (2, "2"), (3, "3"), (4, "4")]


@pytest.mark.parametrize(
    "test_case",
    (CappedMicrobatchScenarioE2ETestCase("virtual capped dependency preserves gap", 0),),
    ids=lambda case: case.description,
)
def test_given_virtual_capped_producer_watermark_jump_when_building_then_frontier_preserves_gap(
    tmp_path: Path, test_case: CappedMicrobatchScenarioE2ETestCase
) -> None:
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_capped_dependency",
        model_sql=timestamp_microbatch_model_sql(
            value_expression="payload",
            batch_concurrency=1,
            replay_policy="forward_only",
            extra_config=(
                "cursor_start '2026-01-01T00:00:00',\n"
                "cursor_end '2026-01-01T12:00:00',\n"
                "microbatch_limit (max_batches 3, action cap_from_end),"
            ),
        ),
    )
    (project_dir / "models" / "downstream_orders.sql").write_text(
        dedent(
            """
            MODEL (
              materialized incremental,
              incremental_strategy delete_insert,
              incremental_mode microbatch,
              microbatch_strategy watermark,
              cursor_watermark_mode all,
              cursor event_time,
              cursor_type timestamp,
              cursor_grain hour,
              cursor_start '2026-01-01T00:00:00',
              cursor_inputs (
                orders (column event_time, roles [filter, watermark]),
              ),
              batch_size 1h,
              lookback 1h,
            );

            SELECT id, event_time, value FROM __ref("orders")
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr
    execute_duckdb(
        db_path=warehouse_path,
        sql=(
            "INSERT INTO raw.raw_events VALUES "
            "(8, '2026-01-01 08:30:00', '8'), "
            "(9, '2026-01-01 09:30:00', '9'), "
            "(10, '2026-01-01 10:30:00', '10')"
        ),
    )

    jumped: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert jumped.returncode == test_case.expected_exit_code, jumped.stdout + jumped.stderr
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id FROM dev__dev.downstream_orders ORDER BY id",
    ) == [(2,), (3,), (4,), (8,), (9,), (10,)]
    assert (
        query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT partition_start, partition_end "
                "FROM sqlbuild_state.microbatch_events "
                "WHERE model_name = 'downstream_orders' "
                "AND record_type = 'partition_completion' "
                "AND partition_start >= '2026-01-01T04:00:00' "
                "AND partition_end <= '2026-01-01T08:00:00'"
            ),
        )
        == []
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="recreated virtual physical target starts a distinct event generation",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_recreated_virtual_physical_target_when_building_then_stale_generation_is_not_inherited(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_microbatch_generation",
        model_sql=timestamp_microbatch_model_sql(
            value_expression="payload",
            batch_concurrency=3,
            replay_policy="forward_only",
        ),
    )
    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    initial_generation: object = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT physical_generation_id FROM sqlbuild_state.microbatch_events "
            "WHERE record_type = 'partition_completion' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )[0][0]
    schema_name, relation_name = physical_orders_relation(state_path=state_path)
    execute_duckdb(
        db_path=warehouse_path,
        sql=(
            f'DROP TABLE "{schema_name}"."{relation_name}"; '
            f'CREATE TABLE "{schema_name}"."{relation_name}" '
            "(id INTEGER, event_time TIMESTAMP, value VARCHAR)"
        ),
    )

    rebuilt: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    latest_generation: object = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT physical_generation_id FROM sqlbuild_state.microbatch_events "
            "WHERE record_type = 'partition_completion' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )[0][0]

    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr
    assert rebuilt.returncode == test_case.expected_exit_code, rebuilt.stdout + rebuilt.stderr
    assert latest_generation != initial_generation
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders ORDER BY id",
    ) == [(1, "1"), (2, "2"), (3, "3"), (4, "4")]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="partial virtual bounded replay retains its requirement and resumes",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_partial_virtual_replay_when_retried_then_same_requirement_completes_new_version(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    f1_sql: str = timestamp_microbatch_model_sql(
        value_expression="CAST(payload AS INTEGER)",
        batch_concurrency=3,
        replay_policy="bounded-4h",
    )
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_microbatch_partial_replay",
        model_sql=f1_sql,
        unaccounted_policy="recover_all",
    )
    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    execute_duckdb(
        db_path=warehouse_path,
        sql="UPDATE raw.raw_events SET payload = 'bad' WHERE id = 2",
    )
    (project_dir / "models" / "orders.sql").write_text(
        timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER) + 10",
            batch_concurrency=3,
            replay_policy="bounded-4h",
        ),
        encoding="utf-8",
    )
    partial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    requirement_before: tuple[object, ...] = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT replay_requirement_id, run_start, run_end, "
            "required_model_version_hash, physical_generation_id "
            "FROM sqlbuild_state.microbatch_events "
            "WHERE record_type = 'replay_requirement' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )[0]
    execute_duckdb(
        db_path=warehouse_path,
        sql="UPDATE raw.raw_events SET payload = '2' WHERE id = 2",
    )

    retried: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    requirement_after: tuple[object, ...] = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT replay_requirement_id, run_start, run_end, "
            "required_model_version_hash, physical_generation_id "
            "FROM sqlbuild_state.microbatch_events "
            "WHERE record_type = 'replay_requirement' "
            "ORDER BY created_at DESC LIMIT 1"
        ),
    )[0]

    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr
    assert partial.returncode != test_case.expected_exit_code
    assert retried.returncode == test_case.expected_exit_code, retried.stdout + retried.stderr
    assert requirement_after == requirement_before
    requirement_id: str = str(requirement_before[0])
    required_version_hash: str = str(requirement_before[3])
    assert (
        query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT COUNT(*) FROM sqlbuild_state.microbatch_events "
                "WHERE record_type = 'partition_completion' "
                f"AND replay_requirement_id = '{requirement_id}' "
                f"AND model_version_hash = '{required_version_hash}'"
            ),
        )[0][0]
        >= test_case.expected_minimum_event_count
    )
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders ORDER BY id",
    ) == [(1, 11), (2, 12), (3, 13), (4, 14)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="virtual all-failed F3 supersedes F2 without resurrecting old requirement",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_all_failed_virtual_f2_and_f3_when_returning_to_f2_then_new_transition_is_created(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_microbatch_supersession",
        model_sql=timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER)",
            batch_concurrency=3,
            replay_policy="bounded-2h",
        ),
        unaccounted_policy="recover_all",
    )
    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    execute_duckdb(
        db_path=warehouse_path,
        sql="UPDATE raw.raw_events SET payload = 'bad'",
    )
    f2_sql: str = timestamp_microbatch_model_sql(
        value_expression="CAST(payload AS INTEGER) + 10",
        batch_concurrency=3,
        replay_policy="bounded-2h",
    )
    f3_sql: str = timestamp_microbatch_model_sql(
        value_expression="CAST(payload AS INTEGER) + 20",
        batch_concurrency=3,
        replay_policy="bounded-2h",
    )
    model_path: Path = project_dir / "models" / "orders.sql"
    model_path.write_text(f2_sql, encoding="utf-8")
    failed_f2: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    model_path.write_text(f3_sql, encoding="utf-8")
    failed_f3: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    model_path.write_text(f2_sql, encoding="utf-8")
    returned_f2: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )

    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr
    assert failed_f2.returncode != test_case.expected_exit_code
    assert failed_f3.returncode != test_case.expected_exit_code
    assert returned_f2.returncode != test_case.expected_exit_code
    requirement_counts: list[tuple[object, ...]] = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT required_model_version_hash, "
            "COUNT(DISTINCT replay_requirement_id) "
            "FROM sqlbuild_state.microbatch_events "
            "WHERE record_type = 'replay_requirement' "
            "GROUP BY required_model_version_hash"
        ),
    )
    assert sorted(int(str(count)) for _version, count in requirement_counts) == [1, 2]
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders ORDER BY id",
    ) == [(1, 1), (2, 2), (3, 3), (4, 4)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="shared history survives promotion and rollback without event copying",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_shared_virtual_microbatch_versions_when_promoting_and_rolling_back_then_events_are_unchanged(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_microbatch_promote_rollback",
        model_sql=timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER)",
            batch_concurrency=3,
            replay_policy="bounded-2h",
        ),
        unaccounted_policy="recover_all",
    )
    dev_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    shared_pr_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    shared_version_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT virtual_environment_name, version_hash "
            "FROM sqlbuild_state.virtual_environment_node_refs "
            "WHERE node_type = 'model' AND node_name = 'orders' "
            "ORDER BY virtual_environment_name"
        ),
    )
    assert len(shared_version_rows) == 2
    assert shared_version_rows[0][1] == shared_version_rows[1][1]
    assert query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT COUNT(DISTINCT scope_key), COUNT(DISTINCT physical_generation_id) "
            "FROM sqlbuild_state.microbatch_events "
            f"WHERE virtual_model_version_hash = '{shared_version_rows[0][1]}'"
        ),
    ) == [(1, 1)]

    (project_dir / "models" / "orders.sql").write_text(
        timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER) + 10",
            batch_concurrency=3,
            replay_policy="bounded-2h",
        ),
        encoding="utf-8",
    )
    changed_pr_build: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--virtual-env", "pr"),
        project_dir=project_dir,
    )
    event_identities_before: list[tuple[object, ...]] = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT event_id, scope_key, physical_generation_id, virtual_model_version_hash "
            "FROM sqlbuild_state.microbatch_events ORDER BY event_id"
        ),
    )
    promoted: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "promote", "--from", "pr", "--to", "dev"),
        project_dir=project_dir,
    )
    event_identities_after_promote: list[tuple[object, ...]] = query_duckdb(
        db_path=state_path,
        sql=(
            "SELECT event_id, scope_key, physical_generation_id, virtual_model_version_hash "
            "FROM sqlbuild_state.microbatch_events ORDER BY event_id"
        ),
    )
    promoted_rows: list[tuple[object, ...]] = query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders ORDER BY id",
    )
    rolled_back: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "rollback", "--virtual-env", "dev"),
        project_dir=project_dir,
    )

    assert dev_build.returncode == test_case.expected_exit_code, dev_build.stdout + dev_build.stderr
    assert shared_pr_build.returncode == test_case.expected_exit_code, (
        shared_pr_build.stdout + shared_pr_build.stderr
    )
    assert changed_pr_build.returncode == test_case.expected_exit_code, (
        changed_pr_build.stdout + changed_pr_build.stderr
    )
    assert promoted.returncode == test_case.expected_exit_code, promoted.stdout + promoted.stderr
    assert rolled_back.returncode == test_case.expected_exit_code, (
        rolled_back.stdout + rolled_back.stderr
    )
    assert len(event_identities_before) >= test_case.expected_minimum_event_count
    assert event_identities_after_promote == event_identities_before
    assert (
        query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT event_id, scope_key, physical_generation_id, virtual_model_version_hash "
                "FROM sqlbuild_state.microbatch_events ORDER BY event_id"
            ),
        )
        == event_identities_before
    )
    assert promoted_rows == [(1, 11), (2, 12), (3, 13), (4, 14)]
    assert query_duckdb(
        db_path=warehouse_path,
        sql="SELECT id, value FROM dev__dev.orders ORDER BY id",
    ) == [(1, 1), (2, 2), (3, 3), (4, 4)]


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualConcurrentMicrobatchE2ETestCase(
            description="active replay roots survive janitor until forward-only supersession",
            expected_exit_code=0,
            expected_minimum_event_count=1,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_orphan_virtual_replay_target_when_janitor_runs_then_only_active_requirement_protects_it(
    test_case: VirtualConcurrentMicrobatchE2ETestCase, tmp_path: Path
) -> None:
    project_dir, warehouse_path, state_path = prepare_virtual_microbatch_lifecycle_project(
        tmp_path=tmp_path,
        project_name="virtual_microbatch_replay_janitor_root",
        model_sql=timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER)",
            batch_concurrency=3,
            replay_policy="bounded-2h",
        ),
        unaccounted_policy="recover_all",
        enable_janitor=True,
    )
    initial: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    execute_duckdb(
        db_path=warehouse_path,
        sql="UPDATE raw.raw_events SET payload = 'bad' WHERE id = 3",
    )
    (project_dir / "models" / "orders.sql").write_text(
        timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER) + 10",
            batch_concurrency=3,
            replay_policy="bounded-2h",
        ),
        encoding="utf-8",
    )
    failed_f2: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    f2_version_hash: str = str(
        query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT required_model_version_hash "
                "FROM sqlbuild_state.microbatch_events "
                "WHERE record_type = 'replay_requirement' "
                "ORDER BY created_at DESC LIMIT 1"
            ),
        )[0][0]
    )
    f2_schema, f2_relation = tuple(
        str(value)
        for value in query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT schema_name, relation_name "
                "FROM sqlbuild_state.physical_relations "
                "WHERE artifact_type = 'model' AND artifact_name = 'orders' "
                f"AND version_hash = '{f2_version_hash}'"
            ),
        )[0]
    )

    protected_janitor: subprocess.CompletedProcess[str] = run_sqb(
        command=("janitor", "--auto-approve"), project_dir=project_dir
    )

    assert initial.returncode == test_case.expected_exit_code, initial.stdout + initial.stderr
    assert failed_f2.returncode != test_case.expected_exit_code
    assert protected_janitor.returncode == test_case.expected_exit_code, (
        protected_janitor.stdout + protected_janitor.stderr
    )
    assert table_exists(
        db_path=warehouse_path,
        schema=f2_schema,
        table_name=f2_relation,
    )

    execute_duckdb(
        db_path=warehouse_path,
        sql="UPDATE raw.raw_events SET payload = CAST(id AS VARCHAR)",
    )
    (project_dir / "models" / "orders.sql").write_text(
        timestamp_microbatch_model_sql(
            value_expression="CAST(payload AS INTEGER) + 20",
            batch_concurrency=3,
            replay_policy="forward_only",
        ),
        encoding="utf-8",
    )
    successful_f3: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build"), project_dir=project_dir
    )
    warehouse_realm: str = str(
        query_duckdb(
            db_path=state_path,
            sql=(
                "SELECT scope_key FROM sqlbuild_state.microbatch_events "
                f"WHERE virtual_model_version_hash = '{f2_version_hash}' LIMIT 1"
            ),
        )[0][0]
    ).split(":")[2]
    execute_duckdb(
        db_path=state_path,
        sql=(
            "INSERT INTO sqlbuild_state.locks "
            "(lock_key, owner_id, expires_at, created_at, updated_at) VALUES "
            f"('model_version:{warehouse_realm}:orders:{f2_version_hash}', "
            "'other-build', CURRENT_TIMESTAMP + INTERVAL 1 HOUR, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
    )
    lease_protected_janitor: subprocess.CompletedProcess[str] = run_sqb(
        command=("janitor", "--auto-approve"), project_dir=project_dir
    )
    assert lease_protected_janitor.returncode == test_case.expected_exit_code, (
        lease_protected_janitor.stdout + lease_protected_janitor.stderr
    )
    assert table_exists(
        db_path=warehouse_path,
        schema=f2_schema,
        table_name=f2_relation,
    )
    execute_duckdb(
        db_path=state_path,
        sql=(
            "DELETE FROM sqlbuild_state.locks "
            f"WHERE lock_key = 'model_version:{warehouse_realm}:orders:{f2_version_hash}'"
        ),
    )
    collecting_janitor: subprocess.CompletedProcess[str] = run_sqb(
        command=("janitor", "--auto-approve"), project_dir=project_dir
    )

    assert successful_f3.returncode == test_case.expected_exit_code, (
        successful_f3.stdout + successful_f3.stderr
    )
    assert collecting_janitor.returncode == test_case.expected_exit_code, (
        collecting_janitor.stdout + collecting_janitor.stderr
    )
    assert not table_exists(
        db_path=warehouse_path,
        schema=f2_schema,
        table_name=f2_relation,
    )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
