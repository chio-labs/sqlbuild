from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner._helpers.graph.model_closure import (
    build_downstream_model_name_closure,
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
            description="collects model names in downstream graph closures",
            expected_downstream_model_names=frozenset(
                {"stg_orders", "fact_orders", "order_rollup"}
            ),
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

    downstream_result: frozenset[str] = build_downstream_model_name_closure(
        start_keys=(SOURCE_ORDERS,),
        downstream_deps=downstream_deps,
    )

    assert downstream_result == test_case.expected_downstream_model_names
