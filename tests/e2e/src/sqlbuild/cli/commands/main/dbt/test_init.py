from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.dbt._test_types import DbtInitDuckDbE2ETestCase
from tests.e2e.src.sqlbuild.cli.commands.main.dbt.helpers import skip_unless_dbt_is_runnable
from tests.e2e.src.sqlbuild.cli.commands.main.shared.helpers import query_duckdb, run_sqb

pytestmark: pytest.MarkDecorator = pytest.mark.dbt


@pytest.mark.parametrize(
    "test_case",
    [
        DbtInitDuckDbE2ETestCase(
            description="dbt init creates minimal SQLBuild project and dbt_profile build works",
            expected_generated_files=("sqlbuild_project.toml",),
            unexpected_generated_paths=("models", "tests", "sources"),
            expected_toml_fragments=(
                'adapter = "duckdb"',
                "[dbt]",
                'project_dir = "../dbt_project"',
                'profiles_dir = "../profiles"',
                'target_path = "../dbt_project/target"',
                'source = "dbt_profile"',
                'profile = "analytics"',
            ),
            unexpected_toml_fragments=("DBT_DUCKDB_PATH",),
            expected_rows=((1,),),
            expected_dbt_stdout_fragments=(
                "dbt execution  dbt build",
                "model",
                "dbt_orders",
                "OK",
            ),
            expected_dbt_fingerprint_rows=(("dbt", "model.analytics.dbt_orders"),),
        )
    ],
    ids=["dbt init creates minimal SQLBuild project and dbt_profile build works"],
)
def test_given_duckdb_dbt_project_when_running_dbt_init_then_generated_project_builds_with_profile(
    tmp_path: Path,
    test_case: DbtInitDuckDbE2ETestCase,
) -> None:
    skip_unless_dbt_is_runnable()
    workspace: Path = tmp_path / "workspace"
    dbt_project_dir: Path = workspace / "dbt_project"
    profiles_dir: Path = workspace / "profiles"
    sqlbuild_project_dir: Path = workspace / "sqlbuild_project"
    db_path: Path = workspace / "warehouse.duckdb"
    (dbt_project_dir / "models").mkdir(parents=True)
    profiles_dir.mkdir(parents=True)
    (dbt_project_dir / "dbt_project.yml").write_text(
        "name: analytics\n"
        "profile: analytics\n"
        "model-paths: ['models']\n"
        "target-path: target\n"
        "models:\n"
        "  analytics:\n"
        "    +materialized: table\n",
        encoding="utf-8",
    )
    (dbt_project_dir / "models" / "dbt_orders.sql").write_text(
        "select 1 as order_id\n",
        encoding="utf-8",
    )
    (profiles_dir / "profiles.yml").write_text(
        "analytics:\n"
        "  target: dev\n"
        "  outputs:\n"
        "    dev:\n"
        "      type: duckdb\n"
        "      path: \"{{ env_var('DBT_DUCKDB_PATH') }}\"\n"
        "      schema: main\n",
        encoding="utf-8",
    )
    env: dict[str, str] = {"DBT_DUCKDB_PATH": db_path.as_posix()}

    init_result: subprocess.CompletedProcess[str] = run_sqb(
        command=(
            "--no-color",
            "dbt",
            "init",
            "--project-dir",
            "dbt_project",
            "--profiles-dir",
            "profiles",
            "--skip-dbt-debug",
        ),
        project_dir=workspace,
        env=env,
    )

    assert init_result.returncode == 0, init_result.stdout + init_result.stderr
    generated_paths: tuple[str, ...] = tuple(
        sorted(path.name for path in sqlbuild_project_dir.iterdir())
    )
    assert generated_paths == test_case.expected_generated_files
    path_name: str
    for path_name in test_case.unexpected_generated_paths:
        assert not (sqlbuild_project_dir / path_name).exists()
    generated_toml: str = (sqlbuild_project_dir / "sqlbuild_project.toml").read_text(
        encoding="utf-8"
    )
    fragment: str
    for fragment in test_case.expected_toml_fragments:
        assert fragment in generated_toml
    for fragment in test_case.unexpected_toml_fragments:
        assert fragment not in generated_toml

    (sqlbuild_project_dir / "models").mkdir()
    (sqlbuild_project_dir / "models" / "local_profile_orders.sql").write_text(
        "MODEL (materialized table);\n\nSELECT 2 AS order_id\n",
        encoding="utf-8",
    )

    plain_build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "build", "--select", "local_profile_orders"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert plain_build_result.returncode == 0, plain_build_result.stdout + plain_build_result.stderr
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id FROM main.local_profile_orders ORDER BY order_id",
    ) == [(2,)]

    (sqlbuild_project_dir / "models" / "downstream_orders.sql").write_text(
        "MODEL (materialized table);\n\n"
        'SELECT order_id FROM __dbt_ref("analytics", "dbt_orders")\n',
        encoding="utf-8",
    )

    build_result: subprocess.CompletedProcess[str] = run_sqb(
        command=("--no-color", "dbt", "build", "--select", "+dbt_orders+"),
        project_dir=sqlbuild_project_dir,
        env=env,
    )

    assert build_result.returncode == 0, build_result.stdout + build_result.stderr
    for fragment in test_case.expected_dbt_stdout_fragments:
        assert fragment in build_result.stdout
    assert query_duckdb(
        db_path=db_path,
        sql="SELECT order_id FROM main.downstream_orders ORDER BY order_id",
    ) == list(test_case.expected_rows)
    assert query_duckdb(
        db_path=db_path,
        sql=(
            "SELECT node_type, node_name FROM main._sqlbuild_fingerprints "
            "WHERE node_type = 'dbt' ORDER BY node_name"
        ),
    ) == list(test_case.expected_dbt_fingerprint_rows)
