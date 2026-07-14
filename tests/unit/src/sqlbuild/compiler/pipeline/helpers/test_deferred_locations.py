"""Tests for deferred target resolution."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from sqlbuild.adapters.bigquery.classes.bigquery_adapter import BigQueryAdapter
from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledProject,
    CompiledRelationLocation,
)
from sqlbuild.compiler.pipeline.helpers.deferred_locations import build_deferred_locations
from sqlbuild.spec.contracts.models import TargetConfig
from tests.unit.src.sqlbuild.compiler.pipeline.helpers._test_types import (
    DeferredTargetTestCase,
)
from tests.unit.src.sqlbuild.compiler.pipeline.helpers.helpers import (
    build_single_model_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        DeferredTargetTestCase(
            description="preserve schema returns logical schema",
            adapter_name="duckdb",
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
            adapter_name="duckdb",
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
            adapter_name="duckdb",
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
            adapter_name="duckdb",
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
            adapter_name="duckdb",
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
            adapter_name="duckdb",
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
        DeferredTargetTestCase(
            description="bigquery deferred locations use adapter-qualified names",
            adapter_name="bigquery",
            logical_schema="analytics",
            logical_database="warehouse",
            env_schema="prod",
            env_database="example-project",
            effective_vars={},
            default_schema="main",
            default_database=None,
            expected_schema="prod",
            expected_database="example-project",
            expected_qualified_name="`example-project.prod.test_model`",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_deferred_target_config_when_building_targets_then_resolves_expected_naming(
    test_case: DeferredTargetTestCase,
) -> None:
    project: CompiledProject = build_single_model_project(
        logical_schema=test_case.logical_schema,
        logical_database=test_case.logical_database,
        physical_schema=test_case.logical_schema or test_case.default_schema,
        physical_database=test_case.logical_database or test_case.default_database,
    )
    deferred_target_config: TargetConfig = TargetConfig(
        schema=test_case.env_schema,
        database=test_case.env_database,
    )

    render_qualified_name: Callable[..., str | None] = (
        BigQueryAdapter().render_qualified_name
        if test_case.adapter_name == "bigquery"
        else DuckDbAdapter().render_qualified_name
    )
    locations: dict[str, CompiledRelationLocation] = build_deferred_locations(
        project=project,
        deferred_target_config=deferred_target_config,
        effective_vars=test_case.effective_vars,
        default_schema=test_case.default_schema,
        default_database=test_case.default_database,
        render_qualified_name=render_qualified_name,
    )

    result: CompiledRelationLocation = locations["test_model"]
    assert result.schema == test_case.expected_schema
    assert result.database == test_case.expected_database
    assert result.qualified_name == test_case.expected_qualified_name
