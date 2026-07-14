from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.classes.duckdb_adapter import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationLocation
from sqlbuild.virtual.executor._helpers.rewrite import (
    build_physical_destination,
    build_rewritten_model_locations,
    relation_type_for_model,
    rewrite_project_model_locations,
)
from tests.unit.src.sqlbuild.virtual.executor._helpers._test_types import (
    PhysicalTargetTestCase,
    RelationTypeTestCase,
    RewriteProjectTargetsTestCase,
    RewrittenTargetsTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor._helpers.helpers import (
    build_adapter,
    build_bound_physical_relation,
    build_virtual_executor_test_project,
)


@pytest.mark.parametrize(
    "test_case",
    [
        PhysicalTargetTestCase(
            description="builds physical target name from model and version hash",
            model_name="fact_orders",
            version_hash="abcdef1234567890",
            expected_schema="dev__sqb_physical",
            expected_name="fact_orders__v_abcdef12",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_model_target_when_building_physical_target_then_it_uses_physical_schema_and_suffix(
    test_case: PhysicalTargetTestCase,
) -> None:
    adapter: DuckDbAdapter = build_adapter()
    project: CompiledProject = build_virtual_executor_test_project()
    target: CompiledRelationLocation = build_physical_destination(
        adapter=adapter,
        target=project.models[1].destination,
        model_name=test_case.model_name,
        version_hash=test_case.version_hash,
    )

    assert target.schema == test_case.expected_schema
    assert target.name == test_case.expected_name


@pytest.mark.parametrize(
    "test_case",
    [
        RewrittenTargetsTestCase(
            description="selected and bound models resolve to physical targets",
            selected_model_version_hashes={"fact_orders": "abcdef1234567890"},
            bound_relations={"stg_orders": "1111111122222222"},
            expected_selected_name="fact_orders__v_abcdef12",
            expected_bound_name="stg_orders__v_11111111",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_selected_and_bound_models_when_rewriting_targets_then_it_uses_physical(
    test_case: RewrittenTargetsTestCase,
) -> None:
    adapter: DuckDbAdapter = build_adapter()
    project: CompiledProject = build_virtual_executor_test_project()

    rewritten_locations: dict[str, CompiledRelationLocation] = build_rewritten_model_locations(
        project=project,
        adapter=adapter,
        selected_model_version_hashes=test_case.selected_model_version_hashes,
        bound_physical_relations={
            model_name: build_bound_physical_relation(
                model_name=model_name,
                version_hash=version_hash,
            )
            for model_name, version_hash in test_case.bound_relations.items()
        },
    )

    assert rewritten_locations["fact_orders"].schema == "dev__sqb_physical"
    assert rewritten_locations["fact_orders"].name == test_case.expected_selected_name
    assert rewritten_locations["stg_orders"].name == test_case.expected_bound_name


@pytest.mark.parametrize(
    "test_case",
    [
        RewriteProjectTargetsTestCase(
            description="project rewrite changes only targeted models",
            selected_model_version_hashes={"fact_orders": "abcdef1234567890"},
            expected_rewritten_name="fact_orders__v_abcdef12",
        )
    ],
    ids=lambda case: case.description,
)
def test_given_rewritten_locations_when_rewriting_project_then_only_model_locations_change(
    test_case: RewriteProjectTargetsTestCase,
) -> None:
    adapter: DuckDbAdapter = build_adapter()
    project: CompiledProject = build_virtual_executor_test_project()
    rewritten_locations: dict[str, CompiledRelationLocation] = build_rewritten_model_locations(
        project=project,
        adapter=adapter,
        selected_model_version_hashes=test_case.selected_model_version_hashes,
        bound_physical_relations={},
    )

    rewritten_project: CompiledProject = rewrite_project_model_locations(
        project=project,
        rewritten_locations=rewritten_locations,
    )

    assert rewritten_project.models[0].destination == project.models[0].destination
    assert rewritten_project.models[1].destination.name == test_case.expected_rewritten_name


@pytest.mark.parametrize(
    "test_case",
    [
        RelationTypeTestCase(
            description="views persist as view relation type",
            materialized="view",
            expected_relation_type="view",
        ),
        RelationTypeTestCase(
            description="tables persist as table relation type",
            materialized="table",
            expected_relation_type="table",
        ),
        RelationTypeTestCase(
            description="incrementals persist as table relation type",
            materialized="incremental",
            expected_relation_type="table",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_materialization_when_resolving_relation_type_then_it_matches_virtual_state(
    test_case: RelationTypeTestCase,
) -> None:
    assert relation_type_for_model(test_case.materialized) == test_case.expected_relation_type
