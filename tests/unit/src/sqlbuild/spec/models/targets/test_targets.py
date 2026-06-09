from __future__ import annotations

import pytest

from sqlbuild.spec.models.exceptions import SpecConfigError
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
    TargetConfigReuseErrorTestCase,
    TargetConfigReuseLocalSourceTestCase,
)

TARGET_CONFIG_REUSE_ERROR_TEST_CASES: list[TargetConfigReuseErrorTestCase] = [
    TargetConfigReuseErrorTestCase(
        description="rejects unknown reuse_from target",
        target_name="dev",
        reuse_from="missing",
        expected_error_fragment="Target 'dev' reuse_from references unknown target 'missing'",
    ),
    TargetConfigReuseErrorTestCase(
        description="rejects self reuse_from target",
        target_name="dev",
        reuse_from="dev",
        expected_error_fragment="Target 'dev' cannot reuse from itself",
    ),
]


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
                        ),
                        reuse_from="prod",
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
                        reuse_hard_copy=True,
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
            expected_reuse_from="prod",
            expected_reuse_hard_copy=True,
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
    assert target_config.reuse_from == test_case.expected_reuse_from
    assert target_config.reuse_hard_copy is test_case.expected_reuse_hard_copy


@pytest.mark.parametrize(
    "test_case",
    TARGET_CONFIG_REUSE_ERROR_TEST_CASES,
    ids=[case.description for case in TARGET_CONFIG_REUSE_ERROR_TEST_CASES],
)
def test_given_invalid_reuse_from_when_resolving_target_then_it_raises(
    test_case: TargetConfigReuseErrorTestCase,
) -> None:
    with pytest.raises(SpecConfigError, match=test_case.expected_error_fragment):
        resolve_target_config(
            project_config=ProjectConfig(
                name="demo",
                adapter="duckdb",
                targets={
                    test_case.target_name: TargetConfig(reuse_from=test_case.reuse_from),
                    "prod": TargetConfig(),
                },
            ),
            local_config=LocalConfig(),
            target_name=test_case.target_name,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        TargetConfigReuseLocalSourceTestCase(
            description="allows reuse_from target defined only in local config",
            expected_reuse_from="prod_local",
        )
    ],
    ids=["allows reuse_from target defined only in local config"],
)
def test_given_reuse_from_exists_only_in_local_config_when_resolving_then_it_is_allowed(
    test_case: TargetConfigReuseLocalSourceTestCase,
) -> None:
    target_config: TargetConfig = resolve_target_config(
        project_config=ProjectConfig(
            name="demo",
            adapter="duckdb",
            targets={"dev": TargetConfig(reuse_from=test_case.expected_reuse_from)},
        ),
        local_config=LocalConfig(targets={test_case.expected_reuse_from: LocalTargetConfig()}),
        target_name="dev",
    )

    assert target_config.reuse_from == test_case.expected_reuse_from
