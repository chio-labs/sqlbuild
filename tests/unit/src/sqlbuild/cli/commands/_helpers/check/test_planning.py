"""Focused Python check planning tests."""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from sqlbuild.adapter.contract.models import RelationLookup
from sqlbuild.cli.commands._helpers.check import core as check_core
from sqlbuild.cli.commands._helpers.check.core import check_dependency_closure
from sqlbuild.cli.commands.exceptions import CliUserError
from sqlbuild.compiler.compile.models import CompiledProject, CompiledRelationLocation
from sqlbuild.compiler.pipeline.models import CompilePipelineResult
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.compiler.python_nodes.models import PythonSqlRunLifecyclePlan
from sqlbuild.executor.python_nodes.models import PythonNodeExecutionResult
from sqlbuild.python_nodes.models import SqlResourceRef
from sqlbuild.python_nodes.types import SqlResourceRefKind
from sqlbuild.spec.contracts.models import SourceEntry
from tests.unit.src.sqlbuild.cli.commands._helpers.check._test_types import (
    CheckPlanningTestCase,
)


@pytest.mark.parametrize(
    "test_case",
    (
        CheckPlanningTestCase(
            description="transitive check dependency closure",
            expected_names=frozenset({"asset", "task", "loader"}),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_check_with_transitive_dependencies_when_planning_then_entire_closure_is_selected(
    test_case: CheckPlanningTestCase,
) -> None:
    graph: Mock = Mock(
        upstream_deps={
            "quality_check": ("asset",),
            "asset": ("task", "loader"),
            "task": (),
            "loader": (),
        }
    )

    selected: frozenset[str] = check_dependency_closure(
        graph=graph, check_names=frozenset({"quality_check"})
    )

    assert selected == test_case.expected_names


@pytest.mark.parametrize(
    "test_case",
    (
        CheckPlanningTestCase(
            description="direct model and source refs are validated without dependency execution",
            expected_names=frozenset({"orders", "raw_orders"}),
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_direct_check_sql_refs_when_preflighting_then_refs_are_validated_without_execution(
    monkeypatch: pytest.MonkeyPatch,
    test_case: CheckPlanningTestCase,
) -> None:
    model_ref: SqlResourceRef = SqlResourceRef(SqlResourceRefKind.MODEL, "orders")
    source_ref: SqlResourceRef = SqlResourceRef(SqlResourceRefKind.SOURCE, "raw_orders")
    refs: frozenset[SqlResourceRef] = frozenset({model_ref, source_ref})
    validated: list[SqlResourceRef] = []
    monkeypatch.setattr(check_core, "build_relation_lookup", lambda **_: Mock())
    monkeypatch.setattr(
        check_core,
        "_validate_check_sql_ref_exists",
        lambda *, ref, **_: validated.append(ref),
    )
    monkeypatch.setattr(
        check_core,
        "create_read_side_python_execution_tracker",
        lambda **_: pytest.fail("direct check refs must not execute as dependencies"),
    )
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=CompiledProject(
            run_id="check-run",
            effective_target_name="dev",
            effective_connection={},
            effective_vars={},
        ),
        plan_output=PlanOutput(
            model_locations={
                "orders": CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="orders",
                    qualified_name="analytics.orders",
                )
            },
            source_map={
                "raw_orders": SourceEntry(
                    name="raw_orders",
                    schema="raw",
                    table="orders",
                )
            },
        ),
    )

    results: tuple[PythonNodeExecutionResult, ...] = check_core.run_check_read_side_dependencies(
        adapter=Mock(),
        connection_config={},
        connection=object(),
        pipeline_result=pipeline_result,
        python_graph=Mock(),
        lifecycle_plan=PythonSqlRunLifecyclePlan(
            ingress_python_node_names=frozenset(),
            ingress_loader_names=frozenset(),
            read_side_sql_keys=frozenset(),
            read_side_python_node_names=frozenset(),
        ),
        relation_targets={model_ref: "analytics.orders", source_ref: "raw.orders"},
        validation_refs=refs,
    )

    assert results == ()
    assert frozenset(ref.name for ref in validated) == test_case.expected_names


@pytest.mark.parametrize(
    "test_case",
    (
        CheckPlanningTestCase(
            description="missing direct model ref fails focused preflight",
            expected_names=frozenset({"orders"}),
            ref_kind="model",
            expected_error_fragment="model 'orders'",
        ),
        CheckPlanningTestCase(
            description="missing direct source ref fails focused preflight",
            expected_names=frozenset({"raw_orders"}),
            ref_kind="source",
            expected_error_fragment="source 'raw_orders'",
        ),
    ),
    ids=lambda case: case.description,
)
def test_given_missing_direct_check_sql_ref_when_preflighting_then_existing_relation_error_is_raised(
    monkeypatch: pytest.MonkeyPatch,
    test_case: CheckPlanningTestCase,
) -> None:
    assert test_case.ref_kind is not None
    assert test_case.expected_error_fragment is not None
    ref: SqlResourceRef = SqlResourceRef(
        SqlResourceRefKind(test_case.ref_kind),
        next(iter(test_case.expected_names)),
    )
    monkeypatch.setattr(
        check_core,
        "build_relation_lookup",
        lambda **_: RelationLookup(relations_by_key={}),
    )
    adapter: Mock = Mock()
    adapter.render_qualified_name.return_value = "analytics.orders"
    pipeline_result: CompilePipelineResult = CompilePipelineResult(
        project=CompiledProject(
            run_id="check-run",
            effective_target_name="dev",
            effective_connection={},
            effective_vars={},
        ),
        plan_output=PlanOutput(
            model_locations={
                "orders": CompiledRelationLocation(
                    database=None,
                    schema="analytics",
                    name="orders",
                    qualified_name="analytics.orders",
                )
            },
            source_map={
                "raw_orders": SourceEntry(
                    name="raw_orders",
                    schema="raw",
                    table="orders",
                )
            },
        ),
    )

    with pytest.raises(CliUserError, match=test_case.expected_error_fragment):
        check_core.run_check_read_side_dependencies(
            adapter=adapter,
            connection_config={},
            connection=object(),
            pipeline_result=pipeline_result,
            python_graph=Mock(),
            lifecycle_plan=PythonSqlRunLifecyclePlan(
                ingress_python_node_names=frozenset(),
                ingress_loader_names=frozenset(),
                read_side_sql_keys=frozenset(),
                read_side_python_node_names=frozenset(),
            ),
            relation_targets={ref: "analytics.orders"},
            validation_refs=frozenset({ref}),
        )


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])
