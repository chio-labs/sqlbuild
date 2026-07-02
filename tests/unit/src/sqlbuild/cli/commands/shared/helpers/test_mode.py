from __future__ import annotations

import pytest

from sqlbuild.cli.commands.shared.exceptions import CliUserError
from sqlbuild.cli.commands.shared.helpers.config.mode import (
    enforce_no_defer_to_in_virtual_mode,
    enforce_standard_mode_command_support,
)
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, SettingsConfig
from tests.unit.src.sqlbuild.cli.commands.shared.helpers._test_types import ModeGuardTestCase


@pytest.mark.parametrize(
    "test_case",
    [
        ModeGuardTestCase(
            description="allows run in standard mode",
            virtual_environments=False,
            command_name="run",
            expected_error_fragment=None,
        )
    ],
    ids=["allows run in standard mode"],
)
def test_given_direct_mode_command_when_enforcing_support_then_allows_execution(
    test_case: ModeGuardTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(virtual_environments=test_case.virtual_environments),
        ),
        local_config=LocalConfig(),
    )

    enforce_standard_mode_command_support(
        discovered_inputs=discovered_inputs,
        command_name=test_case.command_name,
    )
    assert test_case.expected_error_fragment is None


@pytest.mark.parametrize(
    "test_case",
    [
        ModeGuardTestCase(
            description="blocks clone in virtual mode",
            virtual_environments=True,
            command_name="clone",
            expected_error_fragment="clone is not supported when virtual_environments = true",
        )
    ],
    ids=["blocks clone in virtual mode"],
)
def test_given_virtual_mode_command_when_enforcing_support_then_raises_cli_user_error(
    test_case: ModeGuardTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(virtual_environments=test_case.virtual_environments),
        ),
        local_config=LocalConfig(),
    )

    with pytest.raises(CliUserError) as exc_info:
        enforce_standard_mode_command_support(
            discovered_inputs=discovered_inputs,
            command_name=test_case.command_name,
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in exc_info.value.message


@pytest.mark.parametrize(
    "test_case",
    [
        ModeGuardTestCase(
            description="blocks defer-to in virtual mode plan",
            virtual_environments=True,
            command_name="plan",
            defer_to="prod",
            expected_error_fragment=(
                "plan does not support --defer-to when virtual_environments = true"
            ),
        )
    ],
    ids=["blocks defer-to in virtual mode plan"],
)
def test_given_virtual_mode_defer_to_when_enforcing_flag_support_then_raises_cli_user_error(
    test_case: ModeGuardTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            settings=SettingsConfig(virtual_environments=test_case.virtual_environments),
        ),
        local_config=LocalConfig(),
    )

    with pytest.raises(CliUserError) as exc_info:
        enforce_no_defer_to_in_virtual_mode(
            discovered_inputs=discovered_inputs,
            command_name=test_case.command_name,
            defer_to=test_case.defer_to,
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in exc_info.value.message
