from __future__ import annotations

from pathlib import Path

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.exceptions import SpecConfigError
from sqlbuild.spec.models.project import (
    LocalConfig,
    ProjectConfig,
    SettingsConfig,
    StateConfig,
    TargetConfig,
)
from sqlbuild.virtual.state.exceptions import StateBackendConfigError
from sqlbuild.virtual.state.helpers.config import resolve_state_backend_config
from sqlbuild.virtual.state.models import StateBackendConfig
from tests.unit.src.sqlbuild.virtual.state.helpers._test_types import (
    StateBackendConfigResolutionErrorTestCase,
    StateBackendConfigResolutionTestCase,
)

STATE_BACKEND_CONFIG_RESOLUTION_ERROR_TEST_CASES: tuple[
    StateBackendConfigResolutionErrorTestCase, ...
] = (
    StateBackendConfigResolutionErrorTestCase(
        description="blocks unsupported state backend",
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                settings=SettingsConfig(virtual_environments=True),
                default_target="dev",
                targets={
                    "dev": TargetConfig(
                        state=StateConfig(backend="sqlite", schema="sqlbuild_state")
                    )
                },
            ),
            local_config=LocalConfig(),
        ),
        expected_error_type=StateBackendConfigError,
        expected_message_fragment="Unsupported state backend: sqlite",
    ),
    StateBackendConfigResolutionErrorTestCase(
        description="blocks missing state backend",
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                settings=SettingsConfig(virtual_environments=True),
                default_target="dev",
                targets={"dev": TargetConfig(state=StateConfig(schema="sqlbuild_state"))},
            ),
            local_config=LocalConfig(),
        ),
        expected_error_type=StateBackendConfigError,
        expected_message_fragment="does not configure a state backend",
    ),
    StateBackendConfigResolutionErrorTestCase(
        description="blocks missing state schema",
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                settings=SettingsConfig(virtual_environments=True),
                default_target="dev",
                targets={"dev": TargetConfig(state=StateConfig(backend="duckdb"))},
            ),
            local_config=LocalConfig(),
        ),
        expected_error_type=StateBackendConfigError,
        expected_message_fragment="state config must define schema",
    ),
    StateBackendConfigResolutionErrorTestCase(
        description="blocks unknown active target",
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                settings=SettingsConfig(virtual_environments=True),
                default_target="missing",
            ),
            local_config=LocalConfig(),
        ),
        expected_error_type=SpecConfigError,
        expected_message_fragment="Unknown target 'missing'",
    ),
    StateBackendConfigResolutionErrorTestCase(
        description="blocks state commands outside virtual mode",
        discovered_inputs=DiscoveredProjectInputs(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                default_target="dev",
                targets={
                    "dev": TargetConfig(
                        state=StateConfig(backend="duckdb", schema="sqlbuild_state")
                    )
                },
            ),
            local_config=LocalConfig(),
        ),
        expected_error_type=StateBackendConfigError,
        expected_message_fragment="State commands require virtual_environments = true",
    ),
)


@pytest.mark.parametrize(
    "test_case",
    [
        StateBackendConfigResolutionTestCase(
            description="resolves duckdb state config and project-relative database path",
            discovered_inputs=DiscoveredProjectInputs(
                project_config=ProjectConfig(
                    name="demo",
                    adapter="duckdb",
                    settings=SettingsConfig(virtual_environments=True),
                    default_target="dev",
                    targets={
                        "dev": TargetConfig(
                            state=StateConfig(
                                backend="duckdb",
                                schema="sqlbuild_state",
                                connection={"database": "state.duckdb"},
                                allow_reset=True,
                            )
                        )
                    },
                ),
                local_config=LocalConfig(),
            ),
            expected_backend="duckdb",
            expected_schema="sqlbuild_state",
            expected_database_suffix="state.duckdb",
            expected_allow_reset=True,
        )
    ],
    ids=["resolves duckdb state config and project-relative database path"],
)
def test_given_state_config_when_resolving_backend_config_then_returns_effective_config(
    test_case: StateBackendConfigResolutionTestCase,
    tmp_path: Path,
) -> None:
    config: StateBackendConfig = resolve_state_backend_config(
        discovered_inputs=test_case.discovered_inputs,
        project_dir=tmp_path,
    )

    assert config.backend.value == test_case.expected_backend
    assert config.schema == test_case.expected_schema
    assert config.connection["database"] == str(tmp_path / test_case.expected_database_suffix)
    assert config.allow_reset is test_case.expected_allow_reset


@pytest.mark.parametrize(
    "test_case",
    STATE_BACKEND_CONFIG_RESOLUTION_ERROR_TEST_CASES,
    ids=[case.description for case in STATE_BACKEND_CONFIG_RESOLUTION_ERROR_TEST_CASES],
)
def test_given_invalid_state_config_when_resolving_backend_config_then_raises_clear_error(
    test_case: StateBackendConfigResolutionErrorTestCase,
    tmp_path: Path,
) -> None:
    with pytest.raises(test_case.expected_error_type) as exc_info:
        resolve_state_backend_config(
            discovered_inputs=test_case.discovered_inputs,
            project_dir=tmp_path,
        )

    assert test_case.expected_message_fragment in str(exc_info.value)
