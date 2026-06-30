from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.clone._test_types import (
    VirtualCloneE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.clone.helpers import (
    build_dev_target_versions,
    build_prod_source_versions,
    dev_ref_rows,
    dev_seed_ref_rows,
    dev_version_hash,
    init_dev_state,
    insert_dev_model_version_lock,
    prepare_virtual_clone_project,
    prod_seed_version_hash,
    prod_version_hash,
    target_physical_relation_count,
)
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import (
    execute_duckdb,
    query_duckdb,
    run_sqb,
    table_exists,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCloneE2ETestCase(
            description="hydrates workspace hashes from origin warehouse without destination refs",
            command=("--no-color", "clone", "--from", "prod", "--to", "dev"),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "Virtual clone  prod -> dev",
                "mode                    workspace fingerprints",
                "origin state            not used",
                "destination refs        unchanged",
                "hydrated             4",
                "missing in origin    0",
            ),
        )
    ],
    ids=["hydrates workspace hashes from origin warehouse without destination refs"],
)
def test_given_virtual_clone_when_source_has_workspace_versions_then_target_is_hydrated(
    test_case: VirtualCloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_clone_project(tmp_path)
    build_prod_source_versions(project_dir)
    init_dev_state(project_dir)

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert target_physical_relation_count(project_dir) == 4
    assert query_duckdb(
        db_path=project_dir / "dev.duckdb",
        sql=(
            "SELECT id FROM dev__sqb_physical."
            f"stg_orders__v_{prod_version_hash(project_dir, 'stg_orders')[:8]}"
        ),
    ) == [(7,)]
    assert query_duckdb(
        db_path=project_dir / "dev.duckdb",
        sql=(
            "SELECT id FROM dev__sqb_physical."
            f"order_amounts__v_{prod_seed_version_hash(project_dir, 'order_amounts')[:8]}"
        ),
    ) == [(7,)]
    assert dev_ref_rows(project_dir) == []
    assert dev_seed_ref_rows(project_dir) == []


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCloneE2ETestCase(
            description="hydrates destination VDE refs and leaves refs/views unchanged",
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--virtual-env",
                "dev",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "mode                    destination VDE refs",
                "destination VDE         dev",
                "destination refs        unchanged",
                "hydrated             1",
                "already present      3",
            ),
        )
    ],
    ids=["hydrates destination VDE refs and leaves refs/views unchanged"],
)
def test_given_virtual_clone_vde_mode_when_target_artifact_missing_then_only_physical_is_restored(
    test_case: VirtualCloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_clone_project(tmp_path)
    build_prod_source_versions(project_dir)
    build_dev_target_versions(project_dir)
    ref_rows_before: list[tuple[object, ...]] = dev_ref_rows(project_dir)
    view_rows_before: list[tuple[object, ...]] = query_duckdb(
        db_path=project_dir / "dev.duckdb",
        sql="SELECT id FROM dev__dev.stg_orders ORDER BY id",
    )
    missing_hash: str = dev_version_hash(project_dir, "stg_orders")
    execute_duckdb(
        db_path=project_dir / "dev.duckdb",
        sql=f"DROP TABLE dev__sqb_physical.stg_orders__v_{missing_hash[:8]}",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert table_exists(
        db_path=project_dir / "dev.duckdb",
        schema="dev__sqb_physical",
        table_name=f"stg_orders__v_{missing_hash[:8]}",
    )
    assert dev_ref_rows(project_dir) == ref_rows_before
    assert (
        query_duckdb(
            db_path=project_dir / "dev.duckdb",
            sql="SELECT id FROM dev__dev.stg_orders ORDER BY id",
        )
        == view_rows_before
    )


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCloneE2ETestCase(
            description="missing origin artifact reports missing and exits nonzero",
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "stg_orders",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=(
                "missing in origin    1",
                "missing: stg_orders",
            ),
        )
    ],
    ids=["missing origin artifact reports missing and exits nonzero"],
)
def test_given_virtual_clone_when_source_artifact_missing_then_it_reports_missing(
    test_case: VirtualCloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_clone_project(tmp_path)
    build_prod_source_versions(project_dir)
    init_dev_state(project_dir)
    source_hash: str = prod_version_hash(project_dir, "stg_orders")
    execute_duckdb(
        db_path=project_dir / "prod.duckdb",
        sql=f"DROP TABLE prod__sqb_physical.stg_orders__v_{source_hash[:8]}",
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert target_physical_relation_count(project_dir) == 0


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCloneE2ETestCase(
            description="active model-version lock blocks by default",
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--select",
                "stg_orders",
            ),
            expected_exit_code=1,
            expected_stdout_fragments=("model version 'stg_orders:", "is locked"),
        )
    ],
    ids=["active model-version lock blocks by default"],
)
def test_given_virtual_clone_when_target_model_version_locked_then_it_blocks(
    test_case: VirtualCloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_clone_project(tmp_path)
    build_prod_source_versions(project_dir)
    init_dev_state(project_dir)
    version_hash: str = prod_version_hash(project_dir, "stg_orders")
    insert_dev_model_version_lock(
        project_dir=project_dir, model_name="stg_orders", version_hash=version_hash
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stderr
    assert target_physical_relation_count(project_dir) == 0


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualCloneE2ETestCase(
            description="skip locked hydrates other model versions",
            command=(
                "--no-color",
                "clone",
                "--from",
                "prod",
                "--to",
                "dev",
                "--skip-locked",
            ),
            expected_exit_code=0,
            expected_stdout_fragments=(
                "hydrated             3",
                "skipped locked       1",
                "skipped locked: stg_orders",
            ),
        )
    ],
    ids=["skip locked hydrates other model versions"],
)
def test_given_virtual_clone_skip_locked_when_one_version_locked_then_it_hydrates_other_models(
    test_case: VirtualCloneE2ETestCase,
    tmp_path: Path,
) -> None:
    project_dir: Path = prepare_virtual_clone_project(tmp_path)
    build_prod_source_versions(project_dir)
    init_dev_state(project_dir)
    version_hash: str = prod_version_hash(project_dir, "stg_orders")
    insert_dev_model_version_lock(
        project_dir=project_dir, model_name="stg_orders", version_hash=version_hash
    )

    result: subprocess.CompletedProcess[str] = run_sqb(
        command=test_case.command,
        project_dir=project_dir,
    )

    assert result.returncode == test_case.expected_exit_code, result.stderr
    fragment: str
    for fragment in test_case.expected_stdout_fragments:
        assert fragment in result.stdout
    assert target_physical_relation_count(project_dir) == 3
    assert not table_exists(
        db_path=project_dir / "dev.duckdb",
        schema="dev__sqb_physical",
        table_name=f"stg_orders__v_{version_hash[:8]}",
    )
