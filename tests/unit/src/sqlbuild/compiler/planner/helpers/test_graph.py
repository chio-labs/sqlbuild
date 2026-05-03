from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner.helpers.graph import (
    build_downstream_deps,
    build_upstream_deps,
    expand_downstream,
    expand_upstream,
    find_path_keys,
    topologically_order_keys,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    BuildDownstreamDepsTestCase,
    CycleDetectionTestCase,
    ExpandDownstreamTestCase,
    ExpandUpstreamTestCase,
    FindPathKeysErrorTestCase,
    FindPathKeysTestCase,
    TopologicalOrderTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    build_test_project,
    model_key,
    seed_key,
    source_key,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildDownstreamDepsTestCase(
            description="builds downstream edges from upstream deps",
            upstream={
                model_key("orders"): (source_key("raw_orders"),),
                model_key("customers"): (source_key("raw_customers"),),
                model_key("joined"): (model_key("orders"), model_key("customers")),
                source_key("raw_orders"): (),
                source_key("raw_customers"): (),
            },
            expected_downstream_keys={
                source_key("raw_orders"): (model_key("orders"),),
                source_key("raw_customers"): (model_key("customers"),),
                model_key("orders"): (model_key("joined"),),
                model_key("customers"): (model_key("joined"),),
                model_key("joined"): (),
            },
        ),
    ],
    ids=["builds downstream edges from upstream deps"],
)
def test_given_upstream_deps_when_building_downstream_then_returns_expected(
    test_case: BuildDownstreamDepsTestCase,
) -> None:
    result: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        test_case.upstream
    )

    assert result == test_case.expected_downstream_keys


TOPOLOGICAL_ORDER_TEST_CASES: list[TopologicalOrderTestCase] = [
    TopologicalOrderTestCase(
        description="orders a linear chain in dependency order",
        upstream={
            model_key("c"): (model_key("b"),),
            model_key("b"): (model_key("a"),),
            model_key("a"): (),
        },
        expected_order=(model_key("a"), model_key("b"), model_key("c")),
    ),
    TopologicalOrderTestCase(
        description="orders a diamond graph with stable tie-breaking",
        upstream={
            source_key("raw"): (),
            model_key("left"): (source_key("raw"),),
            model_key("right"): (source_key("raw"),),
            model_key("joined"): (model_key("left"), model_key("right")),
        },
        expected_order=(
            source_key("raw"),
            model_key("left"),
            model_key("right"),
            model_key("joined"),
        ),
    ),
    TopologicalOrderTestCase(
        description="includes external dep nodes not in upstream keys",
        upstream={
            model_key("orders"): (source_key("raw_orders"),),
        },
        expected_order=(source_key("raw_orders"), model_key("orders")),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    TOPOLOGICAL_ORDER_TEST_CASES,
    ids=[case.description for case in TOPOLOGICAL_ORDER_TEST_CASES],
)
def test_given_upstream_deps_when_ordering_topologically_then_returns_expected_order(
    test_case: TopologicalOrderTestCase,
) -> None:
    result: tuple[CompiledObjectKey, ...] = topologically_order_keys(test_case.upstream)

    assert result == test_case.expected_order


@pytest.mark.parametrize(
    "test_case",
    [
        CycleDetectionTestCase(
            description="raises on direct cycle between two nodes",
            upstream={
                model_key("a"): (model_key("b"),),
                model_key("b"): (model_key("a"),),
            },
            expected_error_type=ValueError,
        ),
    ],
    ids=["raises on direct cycle between two nodes"],
)
def test_given_cyclic_deps_when_ordering_topologically_then_raises(
    test_case: CycleDetectionTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match="cycle"):
        topologically_order_keys(test_case.upstream)


EXPAND_UPSTREAM_TEST_CASES: list[ExpandUpstreamTestCase] = [
    ExpandUpstreamTestCase(
        description="expands transitive upstream through a chain",
        upstream={
            model_key("c"): (model_key("b"),),
            model_key("b"): (model_key("a"),),
            model_key("a"): (source_key("raw"),),
            source_key("raw"): (),
        },
        key=model_key("c"),
        expected_keys=frozenset({model_key("b"), model_key("a"), source_key("raw")}),
    ),
    ExpandUpstreamTestCase(
        description="returns empty set for root node",
        upstream={
            source_key("raw"): (),
        },
        key=source_key("raw"),
        expected_keys=frozenset(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXPAND_UPSTREAM_TEST_CASES,
    ids=[case.description for case in EXPAND_UPSTREAM_TEST_CASES],
)
def test_given_key_when_expanding_upstream_then_returns_expected_keys(
    test_case: ExpandUpstreamTestCase,
) -> None:
    result: frozenset[CompiledObjectKey] = expand_upstream(test_case.key, test_case.upstream)

    assert result == test_case.expected_keys


EXPAND_DOWNSTREAM_TEST_CASES: list[ExpandDownstreamTestCase] = [
    ExpandDownstreamTestCase(
        description="expands transitive downstream through a chain",
        downstream={
            source_key("raw"): (model_key("a"),),
            model_key("a"): (model_key("b"),),
            model_key("b"): (model_key("c"),),
            model_key("c"): (),
        },
        key=source_key("raw"),
        expected_keys=frozenset({model_key("a"), model_key("b"), model_key("c")}),
    ),
    ExpandDownstreamTestCase(
        description="returns empty set for leaf node",
        downstream={
            model_key("leaf"): (),
        },
        key=model_key("leaf"),
        expected_keys=frozenset(),
    ),
]


@pytest.mark.parametrize(
    "test_case",
    EXPAND_DOWNSTREAM_TEST_CASES,
    ids=[case.description for case in EXPAND_DOWNSTREAM_TEST_CASES],
)
def test_given_key_when_expanding_downstream_then_returns_expected_keys(
    test_case: ExpandDownstreamTestCase,
) -> None:
    result: frozenset[CompiledObjectKey] = expand_downstream(test_case.key, test_case.downstream)

    assert result == test_case.expected_keys


@pytest.mark.parametrize(
    "test_case",
    [
        FindPathKeysTestCase(
            description="finds all nodes on directed paths between start and end",
            downstream={
                source_key("raw"): (model_key("a"),),
                model_key("a"): (model_key("b"), model_key("c")),
                model_key("b"): (model_key("d"),),
                model_key("c"): (model_key("d"),),
                model_key("d"): (),
            },
            start=source_key("raw"),
            end=model_key("d"),
            expected_keys=frozenset(
                {
                    source_key("raw"),
                    model_key("a"),
                    model_key("b"),
                    model_key("c"),
                    model_key("d"),
                }
            ),
        ),
    ],
    ids=["finds all nodes on directed paths between start and end"],
)
def test_given_start_and_end_when_finding_path_keys_then_returns_expected(
    test_case: FindPathKeysTestCase,
) -> None:
    result: frozenset[CompiledObjectKey] = find_path_keys(
        test_case.start, test_case.end, test_case.downstream
    )

    assert result == test_case.expected_keys


@pytest.mark.parametrize(
    "test_case",
    [
        FindPathKeysErrorTestCase(
            description="raises when end is not downstream of start",
            downstream={
                model_key("a"): (model_key("b"),),
                model_key("b"): (),
                model_key("c"): (),
            },
            start=model_key("a"),
            end=model_key("c"),
            expected_error_type=ValueError,
        ),
    ],
    ids=["raises when end is not downstream of start"],
)
def test_given_unreachable_end_when_finding_path_keys_then_raises(
    test_case: FindPathKeysErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match="not downstream"):
        find_path_keys(test_case.start, test_case.end, test_case.downstream)


@pytest.mark.parametrize(
    "test_case",
    [
        TopologicalOrderTestCase(
            description="includes sources and seeds from build_upstream_deps",
            upstream=build_upstream_deps(
                build_test_project(
                    model_deps={"orders": ("raw_orders",)},
                    source_names=("raw_orders",),
                    seed_names=("country_codes",),
                )
            ),
            expected_order=(
                seed_key("country_codes"),
                source_key("raw_orders"),
                model_key("orders"),
            ),
        ),
    ],
    ids=["includes sources and seeds from build_upstream_deps"],
)
def test_given_project_when_building_upstream_and_ordering_then_returns_expected(
    test_case: TopologicalOrderTestCase,
) -> None:
    result: tuple[CompiledObjectKey, ...] = topologically_order_keys(test_case.upstream)

    assert result == test_case.expected_order
