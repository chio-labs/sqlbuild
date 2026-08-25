from __future__ import annotations

import pytest

from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.integrations.dbt._helpers.cli.mode import enforce_dbt_interop_direct_mode
from sqlbuild.integrations.dbt.exceptions import DbtInteropConfigError
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, SettingsConfig
from tests.unit.src.sqlbuild.integrations.dbt._test_types import DbtModeGuardTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        DbtModeGuardTestCase(
            description="allows dbt interop in direct mode",
            virtual_environments=False,
            expected_error_fragment=None,
            expected_code=None,
            expected_help_fragment=None,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_direct_project_mode_when_enforcing_dbt_interop_support_then_allows_execution(
    test_case: DbtModeGuardTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(virtual_environments=test_case.virtual_environments),
        ),
        local_config=LocalConfig(),
    )

    enforce_dbt_interop_direct_mode(discovered_inputs=discovered_inputs)

    assert test_case.expected_code is None


@pytest.mark.parametrize(
    "test_case",
    [
        DbtModeGuardTestCase(
            description="blocks dbt interop in virtual mode",
            virtual_environments=True,
            expected_error_fragment="sqb dbt is not supported when virtual_environments = true",
            expected_code="C241",
            expected_help_fragment="Disable virtual_environments",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_virtual_project_mode_when_enforcing_dbt_interop_support_then_raises_error(
    test_case: DbtModeGuardTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(virtual_environments=test_case.virtual_environments),
        ),
        local_config=LocalConfig(),
    )

    with pytest.raises(DbtInteropConfigError) as exc_info:
        enforce_dbt_interop_direct_mode(discovered_inputs=discovered_inputs)

    error: DbtInteropConfigError = exc_info.value
    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in error.message
    assert error.code == test_case.expected_code
    assert error.help is not None
    assert test_case.expected_help_fragment is not None
    assert test_case.expected_help_fragment in error.help
