from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.graph.model_closure import (
    build_downstream_model_name_closure,
    build_upstream_model_name_closure,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import ModelClosureTestCase

SOURCE_ORDERS: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.SOURCE,
    name="raw_orders",
)
FUNCTION_NORMALIZE: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.UDF,
    name="normalize_order",
)
STG_ORDERS: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="stg_orders",
)
FACT_ORDERS: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="fact_orders",
)
ORDER_ROLLUP: CompiledObjectKey = CompiledObjectKey(
    resource_type=CompiledResourceType.MODEL,
    name="order_rollup",
)


@pytest.mark.parametrize(
    "test_case",
    [
        ModelClosureTestCase(
            description="collects model names in downstream and upstream graph closures",
            expected_downstream_model_names=frozenset(
                {"stg_orders", "fact_orders", "order_rollup"}
            ),
            expected_upstream_model_names=frozenset({"stg_orders", "fact_orders", "order_rollup"}),
        )
    ],
    ids=lambda case: case.description,
)
def test_given_dependency_graph_when_building_model_closures_then_returns_reachable_model_names(
    test_case: ModelClosureTestCase,
) -> None:
    downstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        SOURCE_ORDERS: (FUNCTION_NORMALIZE,),
        FUNCTION_NORMALIZE: (STG_ORDERS,),
        STG_ORDERS: (FACT_ORDERS,),
        FACT_ORDERS: (ORDER_ROLLUP,),
        ORDER_ROLLUP: (),
    }
    upstream_deps: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = {
        SOURCE_ORDERS: (),
        FUNCTION_NORMALIZE: (SOURCE_ORDERS,),
        STG_ORDERS: (FUNCTION_NORMALIZE,),
        FACT_ORDERS: (STG_ORDERS,),
        ORDER_ROLLUP: (FACT_ORDERS,),
    }

    downstream_result: frozenset[str] = build_downstream_model_name_closure(
        start_keys=(SOURCE_ORDERS,),
        downstream_deps=downstream_deps,
    )
    upstream_result: frozenset[str] = build_upstream_model_name_closure(
        start_keys=(ORDER_ROLLUP,),
        upstream_deps=upstream_deps,
    )

    assert downstream_result == test_case.expected_downstream_model_names
    assert upstream_result == test_case.expected_upstream_model_names
