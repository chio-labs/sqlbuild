"""Integration coverage for rejecting model migrations in virtual environments."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.cli.commands.main.model_migrations._test_types import (
    VirtualModeMigrationTestCase,
)
from tests.integration.src.sqlbuild.cli.commands.main.model_migrations.helpers import (
    VIRTUAL_PROJECT_TOML,
    CliRun,
    incremental_orders_sql,
    load_raw_orders,
    run_sqb,
    write_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        VirtualModeMigrationTestCase(
            description="virtual build rejects migrate_from",
            expected_exit_code=1,
            expected_fragment="migrate_from is supported only in direct mode",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_migrate_from_when_building_virtually_then_rejects_before_building(
    test_case: VirtualModeMigrationTestCase, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    write_project(
        project_dir=tmp_path,
        models={"stg_customer_orders": incremental_orders_sql(migrate_from="stg_orders")},
        project_toml=VIRTUAL_PROJECT_TOML,
    )
    load_raw_orders(project_dir=tmp_path, first_day=1, last_day=3)
    initialized: CliRun = run_sqb(project_dir=tmp_path, args=("state", "init"), capsys=capsys)

    result: CliRun = run_sqb(
        project_dir=tmp_path, args=("build", "--virtual-env", "feature"), capsys=capsys
    )

    assert initialized.exit_code == 0, initialized.output
    assert result.exit_code == test_case.expected_exit_code, result.output
    assert test_case.expected_fragment in result.output


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
