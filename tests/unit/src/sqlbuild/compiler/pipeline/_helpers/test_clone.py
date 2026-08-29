from __future__ import annotations

import pytest

from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.clone import prepare_clone_pipeline
from sqlbuild.compiler.pipeline.models import ClonePipelineOptions
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.compiler.pipeline._helpers._test_types import (
    CloneTargetSchemaTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CloneTargetSchemaTestCase(
            description="clone origin named target omits schema strategy",
            origin_schema=None,
            destination_schema="destination",
            expected_target_name="prod",
        ),
        CloneTargetSchemaTestCase(
            description="clone destination named target omits schema strategy",
            origin_schema="origin",
            destination_schema=None,
            expected_target_name="dev",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_clone_target_without_schema_when_compiling_then_fails_before_planning(
    test_case: CloneTargetSchemaTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="test",
            adapter="postgres",
            targets={
                "prod": TargetConfig(schema=test_case.origin_schema),
                "dev": TargetConfig(schema=test_case.destination_schema),
            },
        ),
        local_config=LocalConfig(),
    )

    with pytest.raises(
        ValueError,
        match=f"Named target '{test_case.expected_target_name}' must explicitly set schema",
    ):
        prepare_clone_pipeline(
            discovered_inputs=discovered_inputs,
            adapter=PostgresAdapter(),
            origin_target_name="prod",
            destination_target_name="dev",
            destination_connection=None,
            options=ClonePipelineOptions(),
        )
