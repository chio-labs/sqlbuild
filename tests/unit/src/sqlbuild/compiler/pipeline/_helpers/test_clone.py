from __future__ import annotations

import pytest

from sqlbuild.adapters.postgres.classes.postgres_adapter import PostgresAdapter
from sqlbuild.compiler.discovery.models import DiscoveredProjectInputs
from sqlbuild.compiler.pipeline._helpers.clone import prepare_clone_pipeline
from sqlbuild.compiler.pipeline.models import (
    ClonePipelineConnection,
    ClonePipelineOptions,
    ClonePipelineResult,
)
from sqlbuild.spec.contracts.models import LocalConfig, ProjectConfig, TargetConfig
from tests.unit.src.sqlbuild.compiler.pipeline._helpers._test_types import (
    CloneConnectionInjectionTestCase,
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
            destination_connection=ClonePipelineConnection(config={}, handle=None),
            options=ClonePipelineOptions(),
        )


@pytest.mark.parametrize(
    "test_case",
    [
        CloneConnectionInjectionTestCase(
            description="origin logical namespace uses destination physical connection",
            expected_connection={"database": "destination", "user": "destination-user"},
        )
    ],
    ids=lambda case: case.description,
)
def test_given_clone_targets_when_compiling_then_all_projects_use_destination_connection(
    test_case: CloneConnectionInjectionTestCase,
) -> None:
    discovered_inputs: DiscoveredProjectInputs = DiscoveredProjectInputs(
        project_config=ProjectConfig(
            name="test",
            adapter="postgres",
            targets={
                "prod": TargetConfig(
                    schema="prod",
                    loader_schema="prod",
                    connection={"database": "origin", "password": "${ENV:MISSING}"},
                ),
                "dev": TargetConfig(
                    schema="dev",
                    loader_schema="dev",
                    connection=test_case.expected_connection,
                ),
            },
        ),
        local_config=LocalConfig(),
    )

    result: ClonePipelineResult = prepare_clone_pipeline(
        discovered_inputs=discovered_inputs,
        adapter=PostgresAdapter(),
        origin_target_name="prod",
        destination_target_name="dev",
        destination_connection=ClonePipelineConnection(
            config=test_case.expected_connection,
            handle=None,
        ),
        options=ClonePipelineOptions(),
    )

    assert result.origin_project.effective_target_schema == "prod"
    assert result.destination_project.effective_target_schema == "dev"
    assert result.origin_project.effective_connection == test_case.expected_connection
    assert result.destination_project.effective_connection == test_case.expected_connection
