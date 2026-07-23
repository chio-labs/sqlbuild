from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models import CompiledRelationLocation
from sqlbuild.virtual.planner._helpers.targets import build_destination_from_physical_relation
from sqlbuild.virtual.planner.main._targets import build_virtual_destination_from_physical_relation
from sqlbuild.virtual.state.models import PhysicalRelationRecord
from sqlbuild.virtual.state.types import PhysicalArtifactType
from tests.unit.src.sqlbuild.virtual.planner._helpers._test_types import (
    PhysicalRelationDestinationTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PhysicalRelationDestinationTestCase(
            description="qualifies database schema and name from the stored record",
            database_name="analytics",
            schema_name="sqlbuild_physical",
            relation_name="fact_orders__abc123",
            fallback_logical_schema="dev",
            fallback_logical_database=None,
            expected_qualified_name="analytics.sqlbuild_physical.fact_orders__abc123",
        ),
        PhysicalRelationDestinationTestCase(
            description="qualifies schema and name when the record has no database",
            database_name=None,
            schema_name="sqlbuild_physical",
            relation_name="stg_orders__def456",
            fallback_logical_schema="dev",
            fallback_logical_database="analytics",
            expected_qualified_name="sqlbuild_physical.stg_orders__def456",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_physical_relation_when_building_destination_then_qualifies_location(
    test_case: PhysicalRelationDestinationTestCase,
) -> None:
    relation: PhysicalRelationRecord = PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name=test_case.relation_name.split("__")[0],
        version_hash="hash",
        database_name=test_case.database_name,
        schema_name=test_case.schema_name,
        relation_name=test_case.relation_name,
        relation_type="table",
    )
    fallback: CompiledRelationLocation = CompiledRelationLocation(
        database=None,
        schema="dev",
        name=relation.artifact_name,
        qualified_name="dev." + relation.artifact_name,
        logical_schema=test_case.fallback_logical_schema,
        logical_database=test_case.fallback_logical_database,
    )

    destination: CompiledRelationLocation = build_destination_from_physical_relation(
        adapter=DuckDbAdapter(),
        relation=relation,
        fallback_target=fallback,
    )

    assert destination.qualified_name == test_case.expected_qualified_name
    assert destination.database == test_case.database_name
    assert destination.schema == test_case.schema_name
    assert destination.name == test_case.relation_name
    assert destination.logical_schema == test_case.fallback_logical_schema
    assert destination.logical_database == test_case.fallback_logical_database


@pytest.mark.parametrize(
    "test_case",
    [
        PhysicalRelationDestinationTestCase(
            description="public wrapper delegates to the single canonical implementation",
            database_name="analytics",
            schema_name="sqlbuild_physical",
            relation_name="fact_orders__abc123",
            fallback_logical_schema="dev",
            fallback_logical_database=None,
            expected_qualified_name="analytics.sqlbuild_physical.fact_orders__abc123",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_physical_relation_when_using_public_wrapper_then_matches_canonical_result(
    test_case: PhysicalRelationDestinationTestCase,
) -> None:
    relation: PhysicalRelationRecord = PhysicalRelationRecord(
        artifact_type=PhysicalArtifactType.MODEL,
        artifact_name=test_case.relation_name.split("__")[0],
        version_hash="hash",
        database_name=test_case.database_name,
        schema_name=test_case.schema_name,
        relation_name=test_case.relation_name,
        relation_type="table",
    )
    fallback: CompiledRelationLocation = CompiledRelationLocation(
        database=None,
        schema="dev",
        name=relation.artifact_name,
        qualified_name="dev." + relation.artifact_name,
        logical_schema=test_case.fallback_logical_schema,
        logical_database=test_case.fallback_logical_database,
    )

    wrapped: CompiledRelationLocation = build_virtual_destination_from_physical_relation(
        adapter=DuckDbAdapter(),
        relation=relation,
        fallback_target=fallback,
    )
    canonical: CompiledRelationLocation = build_destination_from_physical_relation(
        adapter=DuckDbAdapter(),
        relation=relation,
        fallback_target=fallback,
    )

    assert wrapped == canonical
    assert wrapped.qualified_name == test_case.expected_qualified_name
