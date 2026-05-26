from __future__ import annotations

import pytest

from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import CompiledProject, CompiledRelationTarget
from sqlbuild.virtual.executor.helpers.rewrite import (
    build_physical_target,
    build_rewritten_model_targets,
    relation_type_for_model,
    rewrite_project_model_targets,
)
from tests.unit.src.sqlbuild.virtual.executor.helpers._test_types import (
    PhysicalTargetTestCase,
    RelationTypeTestCase,
    RewriteProjectTargetsTestCase,
    RewrittenTargetsTestCase,
)
from tests.unit.src.sqlbuild.virtual.executor.helpers.helpers import (
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
    ids=["builds physical target name from model and version hash"],
)
def test_given_model_target_when_building_physical_target_then_it_uses_physical_schema_and_suffix(
    test_case: PhysicalTargetTestCase,
) -> None:
    adapter: DuckDbAdapter = build_adapter()
    project: CompiledProject = build_virtual_executor_test_project()
    target: CompiledRelationTarget = build_physical_target(
        adapter=adapter,
        target=project.models[1].target,
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
    ids=["selected and bound models resolve to physical targets"],
)
def test_given_selected_and_bound_models_when_rewriting_targets_then_it_uses_physical(
    test_case: RewrittenTargetsTestCase,
) -> None:
    adapter: DuckDbAdapter = build_adapter()
    project: CompiledProject = build_virtual_executor_test_project()

    rewritten_targets: dict[str, CompiledRelationTarget] = build_rewritten_model_targets(
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

    assert rewritten_targets["fact_orders"].schema == "dev__sqb_physical"
    assert rewritten_targets["fact_orders"].name == test_case.expected_selected_name
    assert rewritten_targets["stg_orders"].name == test_case.expected_bound_name


@pytest.mark.parametrize(
    "test_case",
    [
        RewriteProjectTargetsTestCase(
            description="project rewrite changes only targeted models",
            selected_model_version_hashes={"fact_orders": "abcdef1234567890"},
            expected_rewritten_name="fact_orders__v_abcdef12",
        )
    ],
    ids=["project rewrite changes only targeted models"],
)
def test_given_rewritten_targets_when_rewriting_project_then_only_model_targets_change(
    test_case: RewriteProjectTargetsTestCase,
) -> None:
    adapter: DuckDbAdapter = build_adapter()
    project: CompiledProject = build_virtual_executor_test_project()
    rewritten_targets: dict[str, CompiledRelationTarget] = build_rewritten_model_targets(
        project=project,
        adapter=adapter,
        selected_model_version_hashes=test_case.selected_model_version_hashes,
        bound_physical_relations={},
    )

    rewritten_project: CompiledProject = rewrite_project_model_targets(
        project=project,
        rewritten_targets=rewritten_targets,
    )

    assert rewritten_project.models[0].target == project.models[0].target
    assert rewritten_project.models[1].target.name == test_case.expected_rewritten_name


RELATION_TYPE_TEST_CASES: list[RelationTypeTestCase] = [
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
]


@pytest.mark.parametrize(
    "test_case",
    RELATION_TYPE_TEST_CASES,
    ids=[case.description for case in RELATION_TYPE_TEST_CASES],
)
def test_given_materialization_when_resolving_relation_type_then_it_matches_virtual_state(
    test_case: RelationTypeTestCase,
) -> None:
    assert relation_type_for_model(test_case.materialized) == test_case.expected_relation_type
