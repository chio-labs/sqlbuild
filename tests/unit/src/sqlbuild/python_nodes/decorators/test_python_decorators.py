"""Tests for public Python node decorator metadata."""

from __future__ import annotations

import pytest

from sqlbuild.assets import asset, get_asset_definition
from sqlbuild.checks import check, get_check_definition
from sqlbuild.shared.models import (
    AssetDefinition,
    CheckDefinition,
    ColumnLineageRef,
    RetryPolicy,
    TaskDefinition,
)
from sqlbuild.shared.types import PythonCheckSeverity
from sqlbuild.tasks import get_task_definition, task
from tests.unit.src.sqlbuild.python_nodes.decorators._test_types import (
    AssetDecoratorMetadataTestCase,
    CheckDecoratorMetadataTestCase,
    TaskDecoratorMetadataTestCase,
)
from tests.unit.src.sqlbuild.python_nodes.decorators.helpers import upstream_asset, upstream_task


@pytest.mark.parametrize(
    "test_case",
    [
        TaskDecoratorMetadataTestCase(
            description="stores task metadata and normalizes single dependency",
            expected_name="fetch_window",
            expected_dep_count=1,
            expected_tags=("api", "hourly"),
            expected_group="ingestion",
            expected_description="Fetch an API window.",
            expected_meta={"owner": "data-eng"},
            expected_retry=RetryPolicy(
                max_attempts=3,
                retry_on=[TimeoutError, ConnectionError],
                initial_delay_seconds=0.5,
                jitter=False,
            ),
        )
    ],
    ids=["stores task metadata and normalizes single dependency"],
)
def test_given_task_decorator_when_reading_definition_then_returns_metadata(
    test_case: TaskDecoratorMetadataTestCase,
) -> None:
    @task(
        name=test_case.expected_name,
        depends_on=upstream_task,
        tags=test_case.expected_tags,
        group=test_case.expected_group,
        meta=test_case.expected_meta,
        retry=test_case.expected_retry,
    )
    def fetch_window(_ctx: object) -> dict[str, object]:
        """Fetch an API window."""

        return {"window": "2026-05-30"}

    definition: TaskDefinition | None = get_task_definition(fetch_window)

    assert definition == TaskDefinition(
        name=test_case.expected_name,
        depends_on=(upstream_task,),
        tags=test_case.expected_tags,
        group=test_case.expected_group,
        description=test_case.expected_description,
        meta=test_case.expected_meta,
        retry=test_case.expected_retry,
    )
    assert definition is not None
    assert len(definition.depends_on) == test_case.expected_dep_count
    assert get_asset_definition(fetch_window) is None


@pytest.mark.parametrize(
    "test_case",
    [
        AssetDecoratorMetadataTestCase(
            description="stores asset schema metadata and column lineage",
            expected_name="export_customers",
            expected_dep_count=1,
            expected_tags=("exports",),
            expected_group="customer_exports",
            expected_description="Published customer export.",
            expected_meta={"format": "parquet"},
            expected_column_names=("customer_id", "email"),
            expected_column_types=("string", "string"),
            expected_column_descriptions=("Stable customer id", None),
            expected_column_lineage={
                "customer_id": (ColumnLineageRef(node="dim_customers", column="customer_id"),),
                "email": (ColumnLineageRef(node="dim_customers", column="email"),),
            },
            expected_retry=RetryPolicy(max_attempts=2, retry_on=TimeoutError, jitter=False),
        )
    ],
    ids=["stores asset schema metadata and column lineage"],
)
def test_given_asset_decorator_when_reading_definition_then_returns_metadata(
    test_case: AssetDecoratorMetadataTestCase,
) -> None:
    @asset(
        name=test_case.expected_name,
        depends_on=[upstream_asset],
        tags=test_case.expected_tags,
        group=test_case.expected_group,
        description=test_case.expected_description,
        meta=test_case.expected_meta,
        columns=[
            {
                "name": "customer_id",
                "type": "string",
                "description": "Stable customer id",
                "meta": {"pii": False},
            },
            {"name": "email", "type": "string", "nullable": True},
        ],
        column_lineage={
            "customer_id": [{"node": "dim_customers", "column": "customer_id"}],
            "email": [{"node": "dim_customers", "column": "email"}],
        },
        retry=test_case.expected_retry,
    )
    def export_customers(_ctx: object) -> dict[str, object]:
        return {"uri": "s3://exports/customers.parquet"}

    definition: AssetDefinition | None = get_asset_definition(export_customers)

    assert definition is not None
    assert definition.name == test_case.expected_name
    assert definition.depends_on == (upstream_asset,)
    assert len(definition.depends_on) == test_case.expected_dep_count
    assert definition.tags == test_case.expected_tags
    assert definition.group == test_case.expected_group
    assert definition.description == test_case.expected_description
    assert definition.meta == test_case.expected_meta
    assert definition.retry == test_case.expected_retry
    assert tuple(column.name for column in definition.columns) == test_case.expected_column_names
    assert tuple(column.type for column in definition.columns) == test_case.expected_column_types
    assert tuple(column.description for column in definition.columns) == (
        test_case.expected_column_descriptions
    )
    assert definition.column_lineage == test_case.expected_column_lineage
    assert get_task_definition(export_customers) is None


@pytest.mark.parametrize(
    "test_case",
    [
        CheckDecoratorMetadataTestCase(
            description="stores check metadata and normalizes dependency list",
            expected_name="export_customers_exists",
            expected_dep_count=1,
            expected_severity=PythonCheckSeverity.WARN,
            expected_tags=("exports",),
            expected_group="customer_exports",
            expected_description="Validate exported customers exist.",
            expected_meta={"owner": "data-eng"},
        )
    ],
    ids=["stores check metadata and normalizes dependency list"],
)
def test_given_check_decorator_when_reading_definition_then_returns_metadata(
    test_case: CheckDecoratorMetadataTestCase,
) -> None:
    @check(
        name=test_case.expected_name,
        depends_on=[upstream_asset],
        severity="warn",
        tags=test_case.expected_tags,
        group=test_case.expected_group,
        meta=test_case.expected_meta,
    )
    def export_customers_exists(_ctx: object) -> bool:
        """Validate exported customers exist."""

        return True

    definition: CheckDefinition | None = get_check_definition(export_customers_exists)

    assert definition == CheckDefinition(
        name=test_case.expected_name,
        depends_on=(upstream_asset,),
        severity=test_case.expected_severity,
        tags=test_case.expected_tags,
        group=test_case.expected_group,
        description=test_case.expected_description,
        meta=test_case.expected_meta,
    )
    assert definition is not None
    assert len(definition.depends_on) == test_case.expected_dep_count
    assert get_asset_definition(export_customers_exists) is None
    assert get_task_definition(export_customers_exists) is None
