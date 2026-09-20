from __future__ import annotations

from dataclasses import replace
from unittest.mock import Mock

import pytest

from sqlbuild.compiler.compile.models import (
    CompiledModel,
    CompiledObjectKey,
    CompiledProject,
    CompiledSqlTest,
    CompileSqlReference,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.fixtures import completion as fixture_completion
from sqlbuild.compiler.planner._helpers.output.plan_output import build_selected_test_entries
from sqlbuild.compiler.planner._helpers.sql_tests import assembly as sql_test_assembly
from sqlbuild.compiler.planner.models import (
    FixtureColumnMetadata,
    FixtureRelationMetadata,
    PlanWarning,
    RelationFixtureCompletion,
    RelationFixturePlanningContext,
    SqlTestPlanEntry,
)
from sqlbuild.compiler.references.types import SqlReferenceKind
from sqlbuild.spec.contracts.models import SettingsConfig
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    CompleteFixturePlanningTestCase,
    FixturePlanningWorkTestCase,
    PlanTestChainTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import PlannerTestAdapter
from tests.unit.src.sqlbuild.compiler.planner._helpers.sql_test_assembly.helpers import (
    build_test_and_project,
)


@pytest.mark.parametrize(
    "test_case",
    (
        FixturePlanningWorkTestCase(
            description="shared project metadata",
            test_count=250,
            expected_metadata_builds=1,
            expected_analysis_calls=1,
            expected_topology_builds=1,
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_many_tests_when_building_entries_then_project_fixture_metadata_is_built_once(
    test_case: FixturePlanningWorkTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compiled_test, project = build_test_and_project(
        PlanTestChainTestCase(
            description=test_case.description,
            model_queries={"orders": 'SELECT order_id FROM __source("raw_orders")'},
            mock_ref_ctes={},
            mock_source_ctes={"raw_orders": "SELECT 1 AS order_id"},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
            expected_cte_bodies={"orders": "SELECT 1 AS order_id"},
        )
    )
    source_reference: CompileSqlReference = CompileSqlReference(
        ref_kind=SqlReferenceKind.SOURCE,
        ref_name="raw_orders",
    )
    model: CompiledModel = replace(
        project.models[0],
        references=(source_reference,),
    )
    tests: tuple[CompiledSqlTest, ...] = tuple(
        replace(
            compiled_test,
            key=CompiledObjectKey(
                resource_type=CompiledResourceType.SQL_TEST,
                name=f"orders_case_{index:04d}",
            ),
            name=f"orders_case_{index:04d}",
        )
        for index in range(test_case.test_count)
    )
    test_project: CompiledProject = replace(
        project,
        models=(model,),
        sql_tests=tests,
        settings=SettingsConfig(sql_analysis=True),
    )
    metadata_builder: Mock = Mock(wraps=fixture_completion._model_fixture_metadata)
    monkeypatch.setattr(fixture_completion, "_model_fixture_metadata", metadata_builder)
    fixture_completion._cached_resolved_column_reads.cache_clear()
    fallback_analyzer: Mock = Mock(wraps=fixture_completion.analyze_resolved_column_reads)
    monkeypatch.setattr(
        fixture_completion,
        "analyze_resolved_column_reads",
        fallback_analyzer,
    )
    topology_builder: Mock = Mock(wraps=sql_test_assembly._topo_sort_model_chain)
    monkeypatch.setattr(sql_test_assembly, "_topo_sort_model_chain", topology_builder)

    entries: list[SqlTestPlanEntry]
    warnings: list[PlanWarning]
    entries, warnings = build_selected_test_entries(
        project=test_project,
        adapter=PlannerTestAdapter(),
        selected_keys=frozenset((model.key,)),
    )

    assert len(entries) == test_case.test_count
    assert warnings == []
    assert metadata_builder.call_count == test_case.expected_metadata_builds
    assert fallback_analyzer.call_count == test_case.expected_analysis_calls
    assert topology_builder.call_count == test_case.expected_topology_builds


@pytest.mark.parametrize(
    "test_case",
    (
        CompleteFixturePlanningTestCase(
            description="complete authoritative fixture",
            fixture_sql="SELECT 1 AS order_id",
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql="SELECT 1 AS order_id",
        ),
        CompleteFixturePlanningTestCase(
            description="explicit typed null fixture",
            fixture_sql="SELECT CAST(NULL AS INTEGER) AS order_id WHERE FALSE",
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql="SELECT CAST(NULL AS INTEGER) AS order_id WHERE FALSE",
        ),
        CompleteFixturePlanningTestCase(
            description="untyped null fixture",
            fixture_sql="SELECT NULL AS order_id WHERE FALSE",
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql=(
                'SELECT\n  CAST("__sqlbuild_partial_fixture".order_id AS INTEGER) '
                "AS order_id\nFROM (\nSELECT NULL AS order_id WHERE FALSE\n) "
                'AS "__sqlbuild_partial_fixture"'
            ),
        ),
        CompleteFixturePlanningTestCase(
            description="untyped null before typed union value",
            fixture_sql=(
                "SELECT NULL AS order_id UNION ALL SELECT CAST(1.5 AS DOUBLE) AS order_id"
            ),
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql=(
                "SELECT NULL AS order_id UNION ALL SELECT CAST(1.5 AS DOUBLE) AS order_id"
            ),
        ),
        CompleteFixturePlanningTestCase(
            description="unquoted mixed-case null fixture",
            fixture_sql="SELECT NULL AS Order_ID WHERE FALSE",
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql=(
                'SELECT\n  CAST("__sqlbuild_partial_fixture".Order_ID AS INTEGER) '
                "AS Order_ID\nFROM (\nSELECT NULL AS Order_ID WHERE FALSE\n) "
                'AS "__sqlbuild_partial_fixture"'
            ),
        ),
        CompleteFixturePlanningTestCase(
            description="quoted mixed-case null fixture",
            fixture_sql='SELECT NULL AS "Order_ID" WHERE FALSE',
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql=(
                'SELECT\n  CAST("__sqlbuild_partial_fixture"."Order_ID" AS INTEGER) '
                'AS "Order_ID"\nFROM (\nSELECT NULL AS "Order_ID" WHERE FALSE\n) '
                'AS "__sqlbuild_partial_fixture"'
            ),
        ),
        CompleteFixturePlanningTestCase(
            description="unknown non-null expression fixture",
            fixture_sql="SELECT custom_value() AS order_id",
            expected_analysis_calls=0,
            expected_inference_calls=1,
            expected_fixture_sql="SELECT custom_value() AS order_id",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_complete_authoritative_fixture_when_completing_then_skips_column_analysis(
    test_case: CompleteFixturePlanningTestCase,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, project = build_test_and_project(
        PlanTestChainTestCase(
            description=test_case.description,
            model_queries={"orders": 'SELECT order_id FROM __source("raw_orders")'},
            mock_ref_ctes={},
            mock_source_ctes={},
            helper_ctes={},
            expected_model_names=("orders",),
            expected_chain_length=1,
        )
    )
    source_reference: CompileSqlReference = CompileSqlReference(
        ref_kind=SqlReferenceKind.SOURCE,
        ref_name="raw_orders",
    )
    model: CompiledModel = replace(project.models[0], references=(source_reference,))
    source_key: tuple[CompiledResourceType, str] = (
        CompiledResourceType.SOURCE,
        "raw_orders",
    )
    context: RelationFixturePlanningContext = RelationFixturePlanningContext(
        models_by_name={model.name: model},
        relations={
            source_key: FixtureRelationMetadata(
                columns=(FixtureColumnMetadata(name="order_id", type="INTEGER", nullable=False),),
                authoritative_names=True,
            )
        },
        authoritative_columns={source_key: frozenset(("order_id",))},
        expected_types={
            source_key: {"order_id": "INTEGER"},
            (CompiledResourceType.MODEL, model.name): {},
        },
    )
    fallback_analyzer: Mock = Mock(
        side_effect=AssertionError("complete fixtures must not trigger model analysis")
    )
    monkeypatch.setattr(
        fixture_completion,
        "analyze_resolved_column_reads",
        fallback_analyzer,
    )
    fixture_inference: Mock = Mock(wraps=fixture_completion.infer_fixture_column_facts)
    monkeypatch.setattr(
        fixture_completion,
        "infer_fixture_column_facts",
        fixture_inference,
    )

    completed: RelationFixtureCompletion = fixture_completion.build_relation_fixture_completion(
        project=replace(project, models=(model,)),
        adapter=PlannerTestAdapter(),
        ordered_model_names=(model.name,),
        fixture_groups=((CompiledResourceType.SOURCE, {"raw_orders": test_case.fixture_sql}),),
        planning_context=context,
    )

    assert completed.diagnostics == ()
    assert completed.fixture_sql_by_key[source_key] == test_case.expected_fixture_sql
    assert fallback_analyzer.call_count == test_case.expected_analysis_calls
    assert fixture_inference.call_count == test_case.expected_inference_calls


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
