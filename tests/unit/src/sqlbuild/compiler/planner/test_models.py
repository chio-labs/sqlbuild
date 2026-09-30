"""Tests for planner model decisions."""

from __future__ import annotations

from dataclasses import replace

import pytest

from sqlbuild.compiler.migrations.types import MigrationDecision
from sqlbuild.compiler.planner.models import ModelMigrationPlanEntry
from sqlbuild.spec.contracts.types import MissingMigrationOriginPolicy
from tests.unit.src.sqlbuild.compiler.planner._test_types import MissingOriginBlockTestCase
from tests.unit.src.sqlbuild.compiler.planner.main.pre_build.helpers import migration_entry


@pytest.mark.parametrize(
    "test_case",
    [
        MissingOriginBlockTestCase(
            description="never-built origin follows allow",
            origin_tracked=False,
            policy=MissingMigrationOriginPolicy.ALLOW,
            expected_blocks=False,
        ),
        MissingOriginBlockTestCase(
            description="never-built origin follows require_confirmation",
            origin_tracked=False,
            policy=MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION,
            expected_blocks=False,
        ),
        MissingOriginBlockTestCase(
            description="never-built origin follows deny",
            origin_tracked=False,
            policy=MissingMigrationOriginPolicy.DENY,
            expected_blocks=True,
        ),
        MissingOriginBlockTestCase(
            description="origin built in this target blocks even under allow",
            origin_tracked=True,
            policy=MissingMigrationOriginPolicy.ALLOW,
            expected_blocks=True,
        ),
        MissingOriginBlockTestCase(
            description="origin built in this target blocks under require_confirmation",
            origin_tracked=True,
            policy=MissingMigrationOriginPolicy.REQUIRE_CONFIRMATION,
            expected_blocks=True,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_missing_origin_when_deciding_then_history_overrides_policy(
    test_case: MissingOriginBlockTestCase,
) -> None:
    entry: ModelMigrationPlanEntry = replace(
        migration_entry(decision=MigrationDecision.ORIGIN_MISSING),
        origin_tracked=test_case.origin_tracked,
        missing_origin_policy=test_case.policy,
    )

    assert entry.blocks_build is test_case.expected_blocks
    assert entry.origin_hidden is test_case.origin_tracked
