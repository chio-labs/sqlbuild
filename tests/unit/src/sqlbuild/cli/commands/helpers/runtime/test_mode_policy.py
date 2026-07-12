from __future__ import annotations

import pytest

from sqlbuild.cli.commands.helpers.runtime.mode_policy import (
    enforce_no_defer_to_in_virtual_mode,
    enforce_virtual_only_flags_in_virtual_mode,
)
from sqlbuild.cli.exceptions import CliUserError
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.spec.models.project import LocalConfig, ProjectConfig, SettingsConfig
from tests.unit.src.sqlbuild.cli.commands.helpers.runtime._test_types import ModeGuardTestCase


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
    ids=lambda case: case.description,
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


@pytest.mark.parametrize(
    "test_case",
    [
        ModeGuardTestCase(
            description="blocks --virtual-env on standard-mode plan",
            virtual_environments=False,
            command_name="plan",
            virtual_env="pr_123",
            expected_error_fragment=(
                "plan does not support --virtual-env unless virtual_environments = true"
            ),
        ),
        ModeGuardTestCase(
            description="blocks --include-stale-upstreams on standard-mode build",
            virtual_environments=False,
            command_name="build",
            include_stale_upstreams=True,
            expected_error_fragment=(
                "build does not support --include-stale-upstreams unless "
                "virtual_environments = true"
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_standard_mode_virtual_only_flags_when_enforcing_then_raises_cli_user_error(
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
        enforce_virtual_only_flags_in_virtual_mode(
            discovered_inputs=discovered_inputs,
            command_name=test_case.command_name,
            virtual_env=test_case.virtual_env,
            include_stale_upstreams=test_case.include_stale_upstreams,
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in exc_info.value.message


@pytest.mark.parametrize(
    "test_case",
    [
        ModeGuardTestCase(
            description="allows both flags in virtual mode",
            virtual_environments=True,
            command_name="plan",
            virtual_env="pr_123",
            include_stale_upstreams=True,
            expected_error_fragment=None,
        ),
        ModeGuardTestCase(
            description="allows standard-mode plan without virtual-only flags",
            virtual_environments=False,
            command_name="plan",
            expected_error_fragment=None,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_supported_virtual_flag_usage_when_enforcing_then_allows_execution(
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

    enforce_virtual_only_flags_in_virtual_mode(
        discovered_inputs=discovered_inputs,
        command_name=test_case.command_name,
        virtual_env=test_case.virtual_env,
        include_stale_upstreams=test_case.include_stale_upstreams,
    )
    assert test_case.expected_error_fragment is None
