from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey
from sqlbuild.compiler.planner._helpers.graph.core import (
    build_downstream_deps,
    build_execution_edge_origins,
    build_execution_upstream_deps,
    expand_downstream,
    expand_upstream,
    find_path_keys,
    topologically_order_keys,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers._test_types import (
    BuildDownstreamDepsTestCase,
    BuildUpstreamDepsTestCase,
    CycleDetectionTestCase,
    ExecutionEdgeOriginsTestCase,
    ExpandDownstreamTestCase,
    ExpandUpstreamTestCase,
    FindPathKeysErrorTestCase,
    FindPathKeysTestCase,
    SqlTestFunctionGraphDepsTestCase,
    TopologicalOrderTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner._helpers.helpers import (
    build_test_project,
    function_key,
    model_key,
    seed_key,
    source_key,
)


@pytest.mark.parametrize(
    "test_case",
    [
        BuildUpstreamDepsTestCase(
            description="keeps attached audit refs out of model deps",
            model_deps={"stg_payments": ("raw_payments",)},
            source_names=("raw_payments", "raw_orders"),
            seed_names=(),
            expected_upstream_keys={
                "stg_payments": ("raw_payments",),
                "raw_payments": (),
                "raw_orders": (),
            },
            audit_model_source_deps={"stg_payments": ("raw_orders",)},
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_building_upstream_then_includes_expected_deps(
    test_case: BuildUpstreamDepsTestCase,
) -> None:
    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(
            build_test_project(
                model_deps=test_case.model_deps,
                source_names=test_case.source_names,
                seed_names=test_case.seed_names,
                audit_model_source_deps=test_case.audit_model_source_deps,
            )
        )
    )

    result: dict[str, tuple[str, ...]] = {}
    for key, deps in upstream.items():
        dep_names: list[str] = []
        for dep in deps:
            dep_names.append(dep.name)
        result[key.name] = tuple(dep_names)

    assert result == test_case.expected_upstream_keys


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
    ids=lambda case: case.description,
)
def test_given_upstream_deps_when_building_downstream_then_returns_expected(
    test_case: BuildDownstreamDepsTestCase,
) -> None:
    result: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = build_downstream_deps(
        test_case.upstream
    )

    assert result == test_case.expected_downstream_keys


@pytest.mark.parametrize(
    "test_case",
    [
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
        TopologicalOrderTestCase(
            description="orders a table function between its upstream and consuming model",
            upstream={
                model_key("customer_order_summary"): (
                    CompiledObjectKey(resource_type="table_fn", name="customer_orders"),
                ),
                CompiledObjectKey(resource_type="table_fn", name="customer_orders"): (
                    model_key("orders"),
                ),
                model_key("orders"): (),
            },
            expected_order=(
                model_key("orders"),
                CompiledObjectKey(resource_type="table_fn", name="customer_orders"),
                model_key("customer_order_summary"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_upstream_deps_when_ordering_topologically_then_returns_expected_order(
    test_case: TopologicalOrderTestCase,
) -> None:
    result: tuple[CompiledObjectKey, ...] = topologically_order_keys(upstream=test_case.upstream)

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
        CycleDetectionTestCase(
            description="raises when a table function and consuming model form a cycle",
            upstream={
                model_key("orders"): (
                    CompiledObjectKey(resource_type="table_fn", name="customer_orders"),
                ),
                CompiledObjectKey(resource_type="table_fn", name="customer_orders"): (
                    model_key("orders"),
                ),
            },
            expected_error_type=ValueError,
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_cyclic_deps_when_ordering_topologically_then_raises(
    test_case: CycleDetectionTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match="cycle"):
        topologically_order_keys(upstream=test_case.upstream)


@pytest.mark.parametrize(
    "test_case",
    [
        CycleDetectionTestCase(
            description="names the injected audit edge that closed the cycle",
            upstream={
                model_key("a"): (model_key("b"),),
                model_key("b"): (model_key("a"),),
            },
            expected_error_type=ValueError,
            injected_edge_origins={
                (model_key("a"), model_key("b")): "audit 'a_audit' on 'a' reads 'b'",
            },
            expected_error_fragment="(via audit 'a_audit' on 'a' reads 'b')",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_injected_edge_cycle_when_ordering_topologically_then_error_names_origin(
    test_case: CycleDetectionTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match="cycle") as exc_info:
        topologically_order_keys(
            upstream=test_case.upstream,
            injected_edge_origins=test_case.injected_edge_origins,
        )

    assert test_case.expected_error_fragment is not None
    assert test_case.expected_error_fragment in str(exc_info.value)


@pytest.mark.parametrize(
    "test_case",
    [
        ExecutionEdgeOriginsTestCase(
            description="does not record audit scope deps as execution edges",
            model_deps={"stg_payments": ("raw_payments",)},
            source_names=("raw_payments", "raw_orders"),
            audit_model_source_deps={"stg_payments": ("raw_orders",)},
            expected_origin_fragments=(),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_audit_scope_deps_when_building_edge_origins_then_names_the_audit(
    test_case: ExecutionEdgeOriginsTestCase,
) -> None:
    origins: dict[tuple[CompiledObjectKey, CompiledObjectKey], str] = build_execution_edge_origins(
        build_test_project(
            model_deps=test_case.model_deps,
            source_names=test_case.source_names,
            audit_model_source_deps=test_case.audit_model_source_deps,
        )
    )

    origin_values: tuple[str, ...] = tuple(sorted(origins.values()))
    assert origin_values == test_case.expected_origin_fragments


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_key_when_expanding_upstream_then_returns_expected_keys(
    test_case: ExpandUpstreamTestCase,
) -> None:
    result: frozenset[CompiledObjectKey] = expand_upstream(
        key=test_case.key, upstream=test_case.upstream
    )

    assert result == test_case.expected_keys


@pytest.mark.parametrize(
    "test_case",
    [
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
    ],
    ids=lambda case: case.description,
)
def test_given_key_when_expanding_downstream_then_returns_expected_keys(
    test_case: ExpandDownstreamTestCase,
) -> None:
    result: frozenset[CompiledObjectKey] = expand_downstream(
        key=test_case.key, downstream=test_case.downstream
    )

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
    ids=lambda case: case.description,
)
def test_given_start_and_end_when_finding_path_keys_then_returns_expected(
    test_case: FindPathKeysTestCase,
) -> None:
    result: frozenset[CompiledObjectKey] = find_path_keys(
        start=test_case.start,
        end=test_case.end,
        downstream=test_case.downstream,
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
    ids=lambda case: case.description,
)
def test_given_unreachable_end_when_finding_path_keys_then_raises(
    test_case: FindPathKeysErrorTestCase,
) -> None:
    with pytest.raises(test_case.expected_error_type, match="not downstream"):
        find_path_keys(
            start=test_case.start,
            end=test_case.end,
            downstream=test_case.downstream,
        )


@pytest.mark.parametrize(
    "test_case",
    [
        TopologicalOrderTestCase(
            description="includes sources and seeds from build_execution_upstream_deps",
            upstream=build_execution_upstream_deps(
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
        TopologicalOrderTestCase(
            description="runs function deps before sql tests for dependent models",
            upstream=build_execution_upstream_deps(
                build_test_project(
                    model_deps={"orders": ("is_completed_order",)},
                    function_names=("is_completed_order",),
                    sql_test_expected_model_names=("orders",),
                )
            ),
            expected_order=(
                function_key("is_completed_order"),
                CompiledObjectKey(
                    resource_type="sql_test",
                    name="test_models",
                ),
                model_key("orders"),
            ),
        ),
        TopologicalOrderTestCase(
            description="runs table function tests after their function resource",
            upstream=build_execution_upstream_deps(
                build_test_project(
                    function_names=("customer_orders",),
                    table_fn_test_function_names=("customer_orders",),
                )
            ),
            expected_order=(
                function_key("customer_orders"),
                CompiledObjectKey(
                    resource_type="sql_test",
                    name="test_table_functions",
                ),
            ),
        ),
        TopologicalOrderTestCase(
            description="runs source refs from attached audits before audited model",
            upstream=build_execution_upstream_deps(
                build_test_project(
                    model_deps={"stg_payments": ("raw_payments",)},
                    source_names=("raw_payments", "raw_orders"),
                    audit_model_source_deps={"stg_payments": ("raw_orders",)},
                )
            ),
            expected_order=(
                source_key("raw_orders"),
                source_key("raw_payments"),
                model_key("stg_payments"),
            ),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_project_when_building_upstream_and_ordering_then_returns_expected(
    test_case: TopologicalOrderTestCase,
) -> None:
    result: tuple[CompiledObjectKey, ...] = topologically_order_keys(upstream=test_case.upstream)

    assert result == test_case.expected_order


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestFunctionGraphDepsTestCase(
            description="sql test depends on functions used by expected model",
            expected_test_upstream_keys=(function_key("is_completed_order"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_sql_test_for_function_model_when_building_upstream_then_test_depends_on_function(
    test_case: SqlTestFunctionGraphDepsTestCase,
) -> None:
    test_key: CompiledObjectKey = CompiledObjectKey(
        resource_type="sql_test",
        name="test_models",
    )

    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(
            build_test_project(
                model_deps={"orders": ("is_completed_order",)},
                function_names=("is_completed_order",),
                sql_test_expected_model_names=("orders",),
            )
        )
    )

    assert upstream[test_key] == test_case.expected_test_upstream_keys


@pytest.mark.parametrize(
    "test_case",
    [
        SqlTestFunctionGraphDepsTestCase(
            description="table function sql test depends directly on tested function",
            expected_test_upstream_keys=(function_key("customer_orders"),),
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_table_function_sql_test_when_building_upstream_then_test_depends_on_function(
    test_case: SqlTestFunctionGraphDepsTestCase,
) -> None:
    test_key: CompiledObjectKey = CompiledObjectKey(
        resource_type="sql_test",
        name="test_table_functions",
    )

    upstream: dict[CompiledObjectKey, tuple[CompiledObjectKey, ...]] = (
        build_execution_upstream_deps(
            build_test_project(
                function_names=("customer_orders",),
                table_fn_test_function_names=("customer_orders",),
            )
        )
    )

    assert upstream[test_key] == test_case.expected_test_upstream_keys
    assert upstream[function_key("customer_orders")] == ()
