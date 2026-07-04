from __future__ import annotations

import pytest

from sqlbuild.executor.pipeline.main.run import _prepare_build_schemas
from tests.unit.src.sqlbuild.executor.pipeline.main._test_types import (
    BuildSchemaPreflightTestCase,
)
from tests.unit.src.sqlbuild.executor.pipeline.main.helpers import (
    BuildSchemaPreflightAdapter,
    build_schema_preflight_plan,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildSchemaPreflightTestCase(
            description="prepares model seed source and function schemas once",
            expected_schemas=((None, "analytics"), (None, "dev"), (None, "raw")),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_build_plan_when_preparing_schemas_then_all_destination_schemas_are_created_once(
    test_case: BuildSchemaPreflightTestCase,
) -> None:
    adapter: BuildSchemaPreflightAdapter = BuildSchemaPreflightAdapter()

    _prepare_build_schemas(
        plan=build_schema_preflight_plan(),
        adapter=adapter,
        connection_config={},
    )

    assert tuple(adapter.prepared_schemas) == test_case.expected_schemas
    assert len(adapter.connections) == 1
    assert adapter.closed_connections == adapter.connections
