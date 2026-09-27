from __future__ import annotations

import pytest

from sqlbuild.spec.contracts.main.resolve_target_config import resolve_target_config
from sqlbuild.spec.contracts.models import (
    AuthoredTimeTravelRetention,
    ExecutionLimitsConfig,
    LocalConfig,
    LocalTargetConfig,
    ProjectConfig,
    TargetConfig,
)
from tests.unit.src.sqlbuild.spec.contracts.main._test_types import (
    ExecutionLimitsResolutionTestCase,
    TargetRetentionResolutionTestCase,
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
