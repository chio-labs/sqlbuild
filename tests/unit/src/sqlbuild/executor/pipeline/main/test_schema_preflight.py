from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.models import PlanOutput
from sqlbuild.executor.pipeline._helpers.graph_width import runnable_graph_width
from sqlbuild.executor.pipeline.main.run import _prepare_build_schemas
from tests.unit.src.sqlbuild.executor.pipeline.main._test_types import (
    BuildSchemaPreflightTestCase,
    RunnableGraphWidthTestCase,
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


@pytest.mark.parametrize(
    "test_case",
    [RunnableGraphWidthTestCase(description="four executable graph nodes", expected_width=4)],
    ids=lambda case: case.description,
)
def test_given_layered_execution_graph_when_sizing_workers_then_uses_largest_frontier(
    test_case: RunnableGraphWidthTestCase,
) -> None:
    root: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.SEED, "root")
    left: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "left")
    right: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "right")
    final: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "final")
    plan: PlanOutput = PlanOutput(
        execution_order=(root, left, right, final),
        upstream_deps={root: (), left: (root,), right: (root,), final: (left, right)},
    )

    assert runnable_graph_width(plan=plan) == test_case.expected_width


@pytest.mark.parametrize(
    "test_case",
    [
        RunnableGraphWidthTestCase(
            description="asymmetric branches retain possible asynchronous overlap",
            expected_width=5,
        )
    ],
    ids=lambda case: case.description,
)
def test_given_asymmetric_dag_when_sizing_workers_then_does_not_underestimate_overlap(
    test_case: RunnableGraphWidthTestCase,
) -> None:
    root: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "root")
    slow: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "slow")
    fast: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "fast")
    fast_child: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "fast_child")
    final: CompiledObjectKey = CompiledObjectKey(CompiledResourceType.MODEL, "final")
    plan: PlanOutput = PlanOutput(
        execution_order=(root, slow, fast, fast_child, final),
        upstream_deps={
            root: (),
            slow: (root,),
            fast: (root,),
            fast_child: (fast,),
            final: (slow, fast_child),
        },
    )

    assert runnable_graph_width(plan=plan) == test_case.expected_width
