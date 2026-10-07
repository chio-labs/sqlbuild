from __future__ import annotations

import pytest

from sqlbuild.spec.contracts.exceptions import SpecConfigError
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import (
    AuthoredTimeTravelRetention,
    ExecutionLimitsConfig,
    LocalConfig,
    LocalTargetConfig,
    ProjectConfig,
    TargetConfig,
    TargetWarehousesConfig,
)
from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy
from tests.unit.src.sqlbuild.spec.contracts.main._test_types import (
    AmbiguousTargetConnectionTestCase,
    ExecutionLimitsResolutionTestCase,
    MissingOriginPolicyResolutionTestCase,
    TargetConnectionDefaultTestCase,
    TargetRetentionResolutionTestCase,
    TargetWarehousesResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetRetentionResolutionTestCase(
            description="local target duration overrides project target duration",
            project_config=ProjectConfig(
                name="demo",
                adapter="snowflake",
                targets={
                    "dev": TargetConfig(
                        time_travel_retention=AuthoredTimeTravelRetention(desired_days=7)
                    )
                },
            ),
            local_config=LocalConfig(
                targets={
                    "dev": LocalTargetConfig(
                        time_travel_retention=AuthoredTimeTravelRetention(desired_days=2)
                    )
                }
            ),
            target_name="dev",
            expected_default=AuthoredTimeTravelRetention(desired_days=2),
        ),
        TargetRetentionResolutionTestCase(
            description="local retention table replaces project target default",
            project_config=ProjectConfig(
                name="demo",
                adapter="snowflake",
                targets={
                    "dev": TargetConfig(
                        time_travel_retention=AuthoredTimeTravelRetention(desired_days=7)
                    )
                },
            ),
            local_config=LocalConfig(
                targets={
                    "dev": LocalTargetConfig(
                        time_travel_retention_by_materialization={
                            "table": AuthoredTimeTravelRetention(desired_days=1)
                        }
                    )
                }
            ),
            target_name="dev",
            expected_default=None,
            expected_by_materialization={"table": AuthoredTimeTravelRetention(desired_days=1)},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_local_target_retention_when_resolving_then_it_overrides_project_target(
    test_case: TargetRetentionResolutionTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        target_name=test_case.target_name,
    )

    assert target_config.time_travel_retention == test_case.expected_default
    assert (
        target_config.time_travel_retention_by_materialization
        == test_case.expected_by_materialization
    )


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionLimitsResolutionTestCase(
            description="local execution fields override project fields independently",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(
                        execution_limits=ExecutionLimitsConfig(
                            max_models=100,
                            max_duration="30m",
                            max_duration_seconds=1_800,
                            remediation="Review the project policy.",
                        )
                    )
                },
            ),
            local_config=LocalConfig(
                targets={
                    "dev": LocalTargetConfig(
                        execution_limits=ExecutionLimitsConfig(
                            max_models=150,
                            remediation="Request approval before continuing.",
                        )
                    )
                }
            ),
            target_name="dev",
            expected_limits=ExecutionLimitsConfig(
                max_models=150,
                max_duration="30m",
                max_duration_seconds=1_800,
                remediation="Request approval before continuing.",
            ),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_local_execution_limit_fields_when_resolving_then_each_field_overrides_project(
    test_case: ExecutionLimitsResolutionTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        target_name=test_case.target_name,
    )

    assert target_config.execution_limits == test_case.expected_limits


@pytest.mark.parametrize(
    "test_case",
    [
        MissingOriginPolicyResolutionTestCase(
            description="local target policy overrides the project target",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(missing_migration_origin=MissingMigrationOriginPolicy.DENY)
                },
            ),
            local_config=LocalConfig(
                targets={
                    "dev": LocalTargetConfig(
                        missing_migration_origin=MissingMigrationOriginPolicy.ALLOW
                    )
                }
            ),
            target_name="dev",
            expected_policy=MissingMigrationOriginPolicy.ALLOW,
        ),
        MissingOriginPolicyResolutionTestCase(
            description="project target policy applies without a local override",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(
                        missing_migration_origin=MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION
                    )
                },
            ),
            local_config=LocalConfig(targets={"dev": LocalTargetConfig()}),
            target_name="dev",
            expected_policy=MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_origin_policy_when_resolving_then_local_overrides_project(
    test_case: MissingOriginPolicyResolutionTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        target_name=test_case.target_name,
    )

    assert target_config.missing_migration_origin is test_case.expected_policy


@pytest.mark.parametrize(
    "test_case",
    [
        TargetWarehousesResolutionTestCase(
            description="local query group overrides only the query group",
            project_warehouses=TargetWarehousesConfig(build="BUILD_WH", query="ADHOC_WH"),
            local_warehouses=TargetWarehousesConfig(query="LOCAL_ADHOC_WH"),
            expected_warehouses=TargetWarehousesConfig(build="BUILD_WH", query="LOCAL_ADHOC_WH"),
        ),
        TargetWarehousesResolutionTestCase(
            description="local groups apply when the project sets none",
            project_warehouses=TargetWarehousesConfig(),
            local_warehouses=TargetWarehousesConfig(build="LOCAL_BUILD_WH"),
            expected_warehouses=TargetWarehousesConfig(build="LOCAL_BUILD_WH"),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_local_target_warehouses_when_resolving_then_each_group_overrides_project(
    test_case: TargetWarehousesResolutionTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=ProjectConfig(
            name="shop",
            adapter="snowflake",
            targets={"dev": TargetConfig(warehouses=test_case.project_warehouses)},
        ),
        local_config=LocalConfig(
            targets={"dev": LocalTargetConfig(warehouses=test_case.local_warehouses)}
        ),
        target_name="dev",
    )

    assert target_config.warehouses == test_case.expected_warehouses


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConnectionDefaultTestCase(
            description="only project connection is used by a target without one",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"local": {"database": "shop.duckdb"}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(),
            expected_connection_name="local",
        ),
        TargetConnectionDefaultTestCase(
            description="local override of the only connection keeps it the default",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"local": {"database": "shop.duckdb"}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(connections={"local": {"database": "mine.duckdb"}}),
            expected_connection_name="local",
        ),
        TargetConnectionDefaultTestCase(
            description="only connection defined locally is used by a project target",
            project_config=ProjectConfig(
                name="shop", adapter="duckdb", targets={"dev": TargetConfig(schema="dev")}
            ),
            local_config=LocalConfig(connections={"local": {"database": "mine.duckdb"}}),
            expected_connection_name="local",
        ),
        TargetConnectionDefaultTestCase(
            description="no named connections keeps the target without one",
            project_config=ProjectConfig(
                name="shop", adapter="duckdb", targets={"dev": TargetConfig(schema="dev")}
            ),
            local_config=LocalConfig(),
            expected_connection_name=None,
        ),
        TargetConnectionDefaultTestCase(
            description="top level project connection block disables the default",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connection={"database": "shop.duckdb"},
                connections={"local": {"database": "other.duckdb"}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(),
            expected_connection_name=None,
        ),
        TargetConnectionDefaultTestCase(
            description="top level local connection block disables the default",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"local": {"database": "shop.duckdb"}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(connection={"database": "mine.duckdb"}),
            expected_connection_name=None,
        ),
        TargetConnectionDefaultTestCase(
            description="inline target connection disables the default",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"local": {"database": "shop.duckdb"}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(
                targets={"dev": LocalTargetConfig(connection={"database": ":memory:"})}
            ),
            expected_connection_name=None,
            expected_inline_connection={"database": ":memory:"},
        ),
        TargetConnectionDefaultTestCase(
            description="explicit target connection is kept among several",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"local": {}, "shared": {}},
                targets={"dev": TargetConfig(schema="dev", connection_name="shared")},
            ),
            local_config=LocalConfig(),
            expected_connection_name="shared",
        ),
        TargetConnectionDefaultTestCase(
            description="local target connection selects among several",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"local": {}, "shared": {}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(targets={"dev": LocalTargetConfig(connection_name="local")}),
            expected_connection_name="local",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_target_without_connection_when_resolving_then_only_named_connection_is_default(
    test_case: TargetConnectionDefaultTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        target_name="dev",
    )

    assert target_config.connection_name == test_case.expected_connection_name
    assert target_config.connection == test_case.expected_inline_connection


@pytest.mark.parametrize(
    "test_case",
    [
        AmbiguousTargetConnectionTestCase(
            description="several project connections",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"shared": {}, "local": {}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(),
            expected_error_fragment=(
                "targets.dev does not set connection and several named connections are defined "
                "(local, shared)"
            ),
        ),
        AmbiguousTargetConnectionTestCase(
            description="project and local connections together",
            project_config=ProjectConfig(
                name="shop",
                adapter="duckdb",
                connections={"shared": {}},
                targets={"dev": TargetConfig(schema="dev")},
            ),
            local_config=LocalConfig(connections={"local": {}}),
            expected_error_fragment="several named connections are defined (local, shared)",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_several_connections_and_target_without_one_when_resolving_then_raises(
    test_case: AmbiguousTargetConnectionTestCase,
) -> None:
    with pytest.raises(SpecConfigError) as error:
        _ = resolve_target_config(
            project_config=test_case.project_config,
            local_config=test_case.local_config,
            target_name="dev",
        )

    assert test_case.expected_error_fragment in str(error.value)
