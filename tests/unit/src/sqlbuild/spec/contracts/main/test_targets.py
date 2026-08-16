from __future__ import annotations

import pytest

from sqlbuild.spec.contracts.main.resolve_effective_changes_only import (
    resolve_effective_changes_only,
)
from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import (
    LocalConfig,
    LocalStateConfig,
    LocalTargetConfig,
    ProjectConfig,
    SettingsConfig,
    StateConfig,
    TargetConfig,
)
from tests.unit.src.sqlbuild.spec.contracts.main._test_types import (
    EffectiveChangesOnlyResolutionTestCase,
    TargetConfigResolutionTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        EffectiveChangesOnlyResolutionTestCase(
            description="uses default false when nothing is configured",
            project_config=ProjectConfig(name="demo", adapter="duckdb"),
            local_config=LocalConfig(),
            cli_changes_only=False,
            expected_changes_only=False,
        ),
        EffectiveChangesOnlyResolutionTestCase(
            description="uses global changes-only setting when target does not override",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                default_target="dev",
                settings=SettingsConfig(changes_only=True),
                targets={"dev": TargetConfig()},
            ),
            local_config=LocalConfig(),
            cli_changes_only=False,
            expected_changes_only=True,
        ),
        EffectiveChangesOnlyResolutionTestCase(
            description="allows target false to override global true",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                default_target="prod",
                settings=SettingsConfig(changes_only=True),
                targets={"prod": TargetConfig(changes_only=False)},
            ),
            local_config=LocalConfig(),
            cli_changes_only=False,
            expected_changes_only=False,
        ),
        EffectiveChangesOnlyResolutionTestCase(
            description="allows CLI changes-only to override target false",
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                default_target="prod",
                targets={"prod": TargetConfig(changes_only=False)},
            ),
            local_config=LocalConfig(),
            cli_changes_only=True,
            expected_changes_only=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_changes_only_config_when_resolving_then_precedence_is_applied(
    test_case: EffectiveChangesOnlyResolutionTestCase,
) -> None:
    changes_only: bool = resolve_effective_changes_only(
        project_config=test_case.project_config,
        local_config=test_case.local_config,
        selected_target=None,
        cli_changes_only=test_case.cli_changes_only,
    )

    assert changes_only is test_case.expected_changes_only


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
                        changes_only=True,
                        loader_schema="raw_shared",
                        state=StateConfig(
                            backend="postgres",
                            schema="sqlbuild_state",
                            connection={"host": "shared-state", "port": 5432},
                            allow_reset=False,
                        ),
                        defer_clone_from="prod",
                    ),
                    "prod": TargetConfig(),
                },
            ),
            local_config=LocalConfig(
                targets={
                    "dev": LocalTargetConfig(
                        state=LocalStateConfig(
                            backend="duckdb",
                            connection={"database": "local-state.duckdb"},
                            allow_reset=True,
                        ),
                        changes_only=False,
                        loader_schema="raw_local",
                        defer_clone_from="staging",
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
            expected_loader_schema="raw_local",
            expected_defer_clone_from="staging",
            expected_changes_only=False,
        )
    ],
    ids=lambda case: case.description,
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
    assert target_config.loader_schema == test_case.expected_loader_schema
    assert target_config.defer_clone_from == test_case.expected_defer_clone_from
    assert target_config.changes_only is test_case.expected_changes_only
