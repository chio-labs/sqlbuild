"""PostgreSQL e2e coverage for auxiliary relation names near the identifier limit."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.e2e.src.sqlbuild.cli.commands.main.postgres._test_types import (
    PostgresLongModelNameE2ETestCase,
)
from tests.e2e.src.sqlbuild.cli.commands.main.postgres.helpers import (
    build_long_model_name_project_files,
    build_postgres_project_toml,
    build_unique_schema_name,
    cleanup_postgres_schema,
    ensure_postgres_schema_ready,
    execute_postgres_sql,
    postgres_relation_names,
)
from tests.e2e.src.sqlbuild.cli.commands.shared.helpers import prepare_inline_project, run_sqb

_TARGET_LENGTH_NAME: str = "regional_fulfillment_order_totals_by_customer"
_STAGING_OVERFLOW_NAME: str = "regional_order_totals_by_cust"
_TOTAL_COLUMN: str = "    total_amount (type BIGINT),\n"


@pytest.mark.parametrize(
    "test_case",
    [
        PostgresLongModelNameE2ETestCase(
            description="long model name builds and passes its scenario",
            model_name=_TARGET_LENGTH_NAME,
            model_columns=_TOTAL_COLUMN,
            expected_exit_code=0,
            expected_scenario_fragments=("PASS=1  FAIL=0  TOTAL=1",),
        ),
        PostgresLongModelNameE2ETestCase(
            description="long model name contract failure leaves no staging relation",
            model_name=_TARGET_LENGTH_NAME,
            model_columns=_TOTAL_COLUMN + "    order_count (type BIGINT),\n",
            expected_exit_code=1,
            expected_scenario_fragments=(
                "runtime contract missing columns: order_count",
                "PASS=0  FAIL=1  TOTAL=1",
            ),
        ),
        PostgresLongModelNameE2ETestCase(
            description="staging-overflow model name contract failure leaves no staging relation",
            model_name=_STAGING_OVERFLOW_NAME,
            model_columns=_TOTAL_COLUMN + "    order_count (type BIGINT),\n",
            expected_exit_code=1,
            expected_scenario_fragments=(
                "runtime contract missing columns: order_count",
                "PASS=0  FAIL=1  TOTAL=1",
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_long_model_name_when_building_and_running_scenario_then_staging_never_collides(
    tmp_path: Path,
    test_case: PostgresLongModelNameE2ETestCase,
    postgres_e2e_config: dict[str, object],
) -> None:
    schema_name: str = build_unique_schema_name(prefix="sqb_long_names")
    project_dir: Path = prepare_inline_project(
        tmp_path=tmp_path,
        project_name="postgres_long_names",
        repo_files=build_long_model_name_project_files(
            project_toml=build_postgres_project_toml(
                project_name="postgres_long_names",
                schema_name=schema_name,
                config=postgres_e2e_config,
            ),
            schema_name=schema_name,
            model_name=test_case.model_name,
            model_columns=test_case.model_columns,
        ),
    )
    ensure_postgres_schema_ready(schema_name=schema_name, config=postgres_e2e_config)
    execute_postgres_sql(
        sql=f"CREATE TABLE {schema_name}.raw_orders AS SELECT 1 AS id, 10 AS amount",
        config=postgres_e2e_config,
    )

    try:
        build: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "build"), project_dir=project_dir
        )
        scenario: subprocess.CompletedProcess[str] = run_sqb(
            command=("--no-color", "scenario", "test"), project_dir=project_dir
        )

        assert build.returncode == test_case.expected_exit_code, build.stdout + build.stderr
        assert scenario.returncode == test_case.expected_exit_code, (
            scenario.stdout + scenario.stderr
        )
        for fragment in test_case.expected_scenario_fragments:
            assert fragment in scenario.stdout, scenario.stdout
        assert (
            postgres_relation_names(
                schema_name=schema_name, name_prefix="__sqb_", config=postgres_e2e_config
            )
            == ()
        )
    finally:
        cleanup_postgres_schema(schema_name=schema_name, config=postgres_e2e_config)


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
