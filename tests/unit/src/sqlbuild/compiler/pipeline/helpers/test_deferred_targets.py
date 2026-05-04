"""Tests for deferred target resolution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationTarget
from sqlbuild.compiler.pipeline.helpers.deferred_targets import build_deferred_targets
from sqlbuild.integrations.duckdb.client import DuckDbAdapter
from sqlbuild.spec.models.project import EnvironmentConfig
from tests.unit.src.sqlbuild.compiler.pipeline.helpers._test_types import (
    DeferredTargetTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline.helpers.helpers import (
    build_single_model_project,
)

DEFERRED_TARGET_TEST_CASES: list[DeferredTargetTestCase] = [
    DeferredTargetTestCase(
        description="preserve schema returns logical schema",
        logical_schema="analytics",
        logical_database=None,
        env_schema="preserve",
        env_database=None,
        effective_vars={},
        default_schema="main",
        default_database=None,
        expected_schema="analytics",
        expected_database=None,
        expected_qualified_name="analytics.test_model",
    ),
    DeferredTargetTestCase(
        description="literal env schema overrides logical schema",
        logical_schema="analytics",
        logical_database=None,
        env_schema="prod_analytics",
        env_database=None,
        effective_vars={},
        default_schema="main",
        default_database=None,
        expected_schema="prod_analytics",
        expected_database=None,
        expected_qualified_name="prod_analytics.test_model",
    ),
    DeferredTargetTestCase(
        description="template env schema resolves CTX with logical value",
        logical_schema="analytics",
        logical_database=None,
        env_schema="prod_${CTX:schema}",
        env_database=None,
        effective_vars={},
        default_schema="main",
        default_database=None,
        expected_schema="prod_analytics",
        expected_database=None,
        expected_qualified_name="prod_analytics.test_model",
    ),
    DeferredTargetTestCase(
        description="template env schema resolves vars",
        logical_schema=None,
        logical_database=None,
        env_schema="dev_${user}",
        env_database=None,
        effective_vars={"user": "kevin"},
        default_schema="main",
        default_database=None,
        expected_schema="dev_kevin",
        expected_database=None,
        expected_qualified_name="dev_kevin.test_model",
    ),
    DeferredTargetTestCase(
        description="none env schema falls through to adapter default",
        logical_schema=None,
        logical_database=None,
        env_schema=None,
        env_database=None,
        effective_vars={},
        default_schema="main",
        default_database=None,
        expected_schema="main",
        expected_database=None,
        expected_qualified_name="main.test_model",
    ),
    DeferredTargetTestCase(
        description="database and schema both resolve for three-part name",
        logical_schema="analytics",
        logical_database="warehouse",
        env_schema="preserve",
        env_database="prod_warehouse",
        effective_vars={},
        default_schema="main",
        default_database=None,
        expected_schema="analytics",
        expected_database="prod_warehouse",
        expected_qualified_name="prod_warehouse.analytics.test_model",
    ),
]


@pytest.mark.parametrize(
    "test_case",
    DEFERRED_TARGET_TEST_CASES,
    ids=[case.description for case in DEFERRED_TARGET_TEST_CASES],
)
def test_given_deferred_env_when_building_targets_then_resolves_expected_naming(
    test_case: DeferredTargetTestCase,
) -> None:
    project: CompiledProject = build_single_model_project(
        logical_schema=test_case.logical_schema,
        logical_database=test_case.logical_database,
        physical_schema=test_case.logical_schema or test_case.default_schema,
        physical_database=test_case.logical_database or test_case.default_database,
    )
    deferred_env: EnvironmentConfig = EnvironmentConfig(
        schema=test_case.env_schema,
        database=test_case.env_database,
    )

    targets: dict[str, CompiledRelationTarget] = build_deferred_targets(
        project=project,
        deferred_env=deferred_env,
        effective_vars=test_case.effective_vars,
        default_schema=test_case.default_schema,
        default_database=test_case.default_database,
        render_qualified_name=DuckDbAdapter().render_qualified_name,
    )

    result: CompiledRelationTarget = targets["test_model"]
    assert result.schema == test_case.expected_schema
    assert result.database == test_case.expected_database
    assert result.qualified_name == test_case.expected_qualified_name
