"""State tables created by an offline Snowflake build are permanent with maximum time travel."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.src.sqlbuild.executor.build.snowflake_metadata._test_types import (
    StateTableRetentionTestCase,
)
from tests.integration.src.sqlbuild.executor.build.snowflake_metadata.helpers import (
    OfflineBuild,
    SimulatedSnowflakeWarehouse,
    build_offline_snowflake_project,
    failed_models,
    orders_warehouse,
    state_table_creates,
    write_orders_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateTableRetentionTestCase(
            description="enterprise account keeps 90 days",
            max_retention_days=90,
            expected_first_retention_days="90",
            expected_later_retention_days=frozenset({"90"}),
        ),
        StateTableRetentionTestCase(
            description="standard account retries once and then creates with 1 day",
            max_retention_days=1,
            expected_first_retention_days="90",
            expected_later_retention_days=frozenset({"1"}),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_account_edition_when_building_then_state_tables_are_permanent_with_max_retention(
    test_case: StateTableRetentionTestCase, tmp_path: Path
) -> None:
    write_orders_project(project_dir=tmp_path)
    warehouse: SimulatedSnowflakeWarehouse = orders_warehouse()
    warehouse.max_retention_days = test_case.max_retention_days

    build: OfflineBuild = build_offline_snowflake_project(
        project_dir=tmp_path, warehouse=warehouse, max_concurrency=1
    )
    creates: tuple[str, ...] = state_table_creates(build)

    assert failed_models(build) == ()
    assert len(creates) > 1
    assert all(create.startswith("CREATE TABLE IF NOT EXISTS ") for create in creates)
    assert all("._sqlbuild_fingerprints (" in create for create in creates)
    assert creates[0].rsplit(" = ", 1)[1] == test_case.expected_first_retention_days
    assert {
        create.rsplit(" = ", 1)[1] for create in creates[1:]
    } == test_case.expected_later_retention_days
