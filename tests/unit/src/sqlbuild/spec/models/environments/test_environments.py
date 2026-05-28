from __future__ import annotations

import pytest

from sqlbuild.spec.models.environments import resolve_environment_config
from sqlbuild.spec.models.project import (
    EnvironmentConfig,
    LocalConfig,
    LocalEnvironmentConfig,
    LocalStateConfig,
    ProjectConfig,
    StateConfig,
)
from tests.unit.src.sqlbuild.spec.models.environments._test_types import (
    EnvironmentConfigResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EnvironmentConfigResolutionTestCase(
            description="merges local state overrides over project state config",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                environments={
                    "dev": EnvironmentConfig(
                        state=StateConfig(
                            backend="postgres",
                            schema="sqlbuild_state",
                            connection={"host": "shared-state", "port": 5432},
                            allow_reset=False,
                        )
                    )
                },
            ),
            local_config=LocalConfig(
                environments={
                    "dev": LocalEnvironmentConfig(
                        state=LocalStateConfig(
                            backend="duckdb",
                            connection={"database": "local-state.duckdb"},
                            allow_reset=True,
                        )
                    )
                }
            ),
            environment_name="dev",
            expected_backend="duckdb",
            expected_schema="sqlbuild_state",
            expected_connection={
                "host": "shared-state",
                "port": 5432,
                "database": "local-state.duckdb",
            },
            expected_allow_reset=True,
        )
    ],
    ids=["merges local state overrides over project state config"],
)
def test_given_project_and_local_state_config_when_resolving_then_local_overrides_are_applied(
    test_case: EnvironmentConfigResolutionTestCase,
) -> None:
    environment_config: EnvironmentConfig = resolve_environment_config(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        environment_name=test_case.environment_name,
    )

    assert environment_config.state.backend == test_case.expected_backend
    assert environment_config.state.schema == test_case.expected_schema
    assert environment_config.state.connection == test_case.expected_connection
    assert environment_config.state.allow_reset is test_case.expected_allow_reset
