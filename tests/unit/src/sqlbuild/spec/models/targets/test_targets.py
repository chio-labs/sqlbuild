from __future__ import annotations

import pytest

from sqlbuild.spec.models.project import (
    LocalConfig,
    LocalStateConfig,
    LocalTargetConfig,
    ProjectConfig,
    StateConfig,
    TargetConfig,
)
from sqlbuild.spec.models.targets import resolve_target_config
from tests.unit.src.sqlbuild.spec.models.targets._test_types import (
    TargetConfigResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConfigResolutionTestCase(
            description="merges local state overrides over project state config",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    "dev": TargetConfig(
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
                targets={
                    "dev": LocalTargetConfig(
                        state=LocalStateConfig(
                            backend="duckdb",
                            connection={"database": "local-state.duckdb"},
                            allow_reset=True,
                        )
                    )
                }
            ),
            target_name="dev",
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
    test_case: TargetConfigResolutionTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        target_name=test_case.target_name,
    )

    assert target_config.state.backend == test_case.expected_backend
    assert target_config.state.schema == test_case.expected_schema
    assert target_config.state.connection == test_case.expected_connection
    assert target_config.state.allow_reset is test_case.expected_allow_reset
