from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledModel, CompiledProject
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.lineage.main.columns import build_project_column_lineage
from sqlbuild.compiler.lineage.models import ColumnLineage, ModelColumnLineage, ProjectColumnLineage
from sqlbuild.compiler.lineage.types import ColumnLineageConfidence, ColumnTransformKind
from tests.unit.src.sqlbuild.compiler.lineage._test_types import (
    ColumnLineageAnalyzerTestCase,
    ProjectLineageGraphTestCase,
    SqlglotDisabledLineageTestCase,
)
from tests.unit.src.sqlbuild.compiler.lineage.helpers import (
    edge_label,
    make_compiled_model,
    make_compiled_project,
    make_compiled_seed,
)

ANALYZER_TEST_CASES: list[ColumnLineageAnalyzerTestCase] = [
    ColumnLineageAnalyzerTestCase(
        description="infers direct model column passthrough",
        model_name="orders_out",
        query_sql='SELECT order_id FROM __ref("orders")',
        inferred_columns=("order_id",),
        upstream_model_columns={"orders": ("order_id",)},
        upstream_seed_columns={},
        expected_column="order_id",
        expected_upstream_columns=("model:orders.order_id",),
        expected_transform_kind=ColumnTransformKind.DIRECT,
    ),
    ColumnLineageAnalyzerTestCase(
        description="infers aliased model column passthrough",
        model_name="orders_out",
        query_sql='SELECT id AS order_id FROM __ref("orders")',
        inferred_columns=("order_id",),
        upstream_model_columns={"orders": ("id",)},
        upstream_seed_columns={},
        expected_column="order_id",
        expected_upstream_columns=("model:orders.id",),
        expected_transform_kind=ColumnTransformKind.DIRECT,
    ),
    ColumnLineageAnalyzerTestCase(
        description="classifies casts",
        model_name="payments_out",
        query_sql='SELECT CAST(amount AS DECIMAL(10, 2)) AS amount_decimal FROM __ref("payments")',
        inferred_columns=("amount_decimal",),
        upstream_model_columns={"payments": ("amount",)},
        upstream_seed_columns={},
        expected_column="amount_decimal",
        expected_upstream_columns=("model:payments.amount",),
        expected_transform_kind=ColumnTransformKind.CAST,
    ),
    ColumnLineageAnalyzerTestCase(
        description="infers multi-column arithmetic expression",
        model_name="orders_out",
        query_sql='SELECT quantity * price_cents AS total_cents FROM __ref("orders")',
        inferred_columns=("total_cents",),
        upstream_model_columns={"orders": ("quantity", "price_cents")},
        upstream_seed_columns={},
        expected_column="total_cents",
        expected_upstream_columns=("model:orders.price_cents", "model:orders.quantity"),
        expected_transform_kind=ColumnTransformKind.EXPRESSION,
    ),
    ColumnLineageAnalyzerTestCase(
        description="infers join expression across model and seed",
        model_name="orders_out",
        query_sql=(
            'SELECT o.quantity * w.price_cents AS total_cents FROM __ref("orders") o '
            'JOIN __seed("waffle_types") w ON o.waffle_type_id = w.waffle_type_id'
        ),
        inferred_columns=("total_cents",),
        upstream_model_columns={"orders": ("quantity", "waffle_type_id")},
        upstream_seed_columns={"waffle_types": ("price_cents", "waffle_type_id")},
        expected_column="total_cents",
        expected_upstream_columns=("model:orders.quantity", "seed:waffle_types.price_cents"),
        expected_transform_kind=ColumnTransformKind.EXPRESSION,
    ),
    ColumnLineageAnalyzerTestCase(
        description="classifies aggregations",
        model_name="payments_out",
        query_sql=(
            'SELECT customer_id, SUM(amount_cents) AS revenue_cents FROM __ref("payments") '
            "GROUP BY customer_id"
        ),
        inferred_columns=("customer_id", "revenue_cents"),
        upstream_model_columns={"payments": ("customer_id", "amount_cents")},
        upstream_seed_columns={},
        expected_column="revenue_cents",
        expected_upstream_columns=("model:payments.amount_cents",),
        expected_transform_kind=ColumnTransformKind.AGGREGATION,
    ),
    ColumnLineageAnalyzerTestCase(
        description="keeps CTE nodes internally while collapsing upstream dependency",
        model_name="payments_out",
        query_sql=(
            'WITH x AS (SELECT amount_cents FROM __ref("payments")) SELECT amount_cents FROM x'
        ),
        inferred_columns=("amount_cents",),
        upstream_model_columns={"payments": ("amount_cents",)},
        upstream_seed_columns={},
        expected_column="amount_cents",
        expected_upstream_columns=("model:payments.amount_cents",),
        expected_transform_kind=ColumnTransformKind.DIRECT,
        expected_internal_scope_names=("x",),
    ),
    ColumnLineageAnalyzerTestCase(
        description="infers both branches of a union",
        model_name="unioned",
        query_sql='SELECT id FROM __ref("a") UNION ALL SELECT id FROM __ref("b")',
        inferred_columns=("id",),
        upstream_model_columns={"a": ("id",), "b": ("id",)},
        upstream_seed_columns={},
        expected_column="id",
        expected_upstream_columns=("model:a.id", "model:b.id"),
        expected_transform_kind=ColumnTransformKind.DIRECT,
    ),
    ColumnLineageAnalyzerTestCase(
        description="classifies constants with no upstream columns",
        model_name="constants",
        query_sql="SELECT 1 AS one",
        inferred_columns=("one",),
        upstream_model_columns={},
        upstream_seed_columns={},
        expected_column="one",
        expected_upstream_columns=(),
        expected_transform_kind=ColumnTransformKind.CONSTANT,
    ),
]


@pytest.mark.parametrize(
    "test_case",
    ANALYZER_TEST_CASES,
    ids=[case.description for case in ANALYZER_TEST_CASES],
)
def test_given_compiled_project_when_building_column_lineage_then_infers_expected_column(
    test_case: ColumnLineageAnalyzerTestCase,
) -> None:
    upstream_models: tuple[CompiledModel, ...] = tuple(
        make_compiled_model(
            name=model_name,
            query_sql="SELECT 1",
            inferred_columns=columns,
        )
        for model_name, columns in test_case.upstream_model_columns.items()
    )
    target_model: CompiledModel = make_compiled_model(
        name=test_case.model_name,
        query_sql=test_case.query_sql,
        inferred_columns=test_case.inferred_columns,
    )
    project: CompiledProject = make_compiled_project(
        models=upstream_models + (target_model,),
        seeds=tuple(
            make_compiled_seed(name=seed_name, columns=columns)
            for seed_name, columns in test_case.upstream_seed_columns.items()
        ),
    )

    result: ProjectColumnLineage | None = build_project_column_lineage(project)

    assert result is not None
    model_lineage: ModelColumnLineage = result.models[test_case.model_name]
    column_lineage: ColumnLineage = next(
        column
        for column in model_lineage.columns
        if column.output_column == test_case.expected_column
    )
    upstream_columns: tuple[str, ...] = tuple(
        sorted(
            f"{CompiledResourceType(source.resource_type).value}:{source.resource_name}.{source.column_name}"
            for source in column_lineage.upstream_columns
        )
    )
    assert upstream_columns == tuple(sorted(test_case.expected_upstream_columns))
    assert column_lineage.transform_kind == test_case.expected_transform_kind
    for expected_scope_name in test_case.expected_internal_scope_names:
        assert expected_scope_name in {node.scope_name for node in column_lineage.nodes}


@pytest.mark.parametrize(
    "test_case",
    [
        ColumnLineageAnalyzerTestCase(
            description="expands select star from known upstream schema with medium confidence",
            model_name="orders_out",
            query_sql='SELECT * FROM __ref("orders")',
            inferred_columns=None,
            upstream_model_columns={"orders": ("order_id", "amount_cents")},
            upstream_seed_columns={},
            expected_column="order_id",
            expected_upstream_columns=("model:orders.order_id",),
            expected_transform_kind=ColumnTransformKind.STAR,
        )
    ],
    ids=["expands select star from known upstream schema with medium confidence"],
)
def test_given_select_star_when_building_column_lineage_then_expands_known_schema_columns(
    test_case: ColumnLineageAnalyzerTestCase,
) -> None:
    project: CompiledProject = make_compiled_project(
        models=(
            make_compiled_model(
                name="orders",
                query_sql="SELECT 1",
                inferred_columns=("order_id", "amount_cents"),
            ),
            make_compiled_model(
                name=test_case.model_name,
                query_sql=test_case.query_sql,
                inferred_columns=test_case.inferred_columns,
            ),
        )
    )

    result: ProjectColumnLineage | None = build_project_column_lineage(project)

    assert result is not None
    model_lineage: ModelColumnLineage = result.models[test_case.model_name]
    order_id_lineage: ColumnLineage = next(
        column for column in model_lineage.columns if column.output_column == "order_id"
    )
    assert model_lineage.has_star
    assert order_id_lineage.transform_kind == test_case.expected_transform_kind
    assert order_id_lineage.confidence == ColumnLineageConfidence.MEDIUM


@pytest.mark.parametrize(
    "test_case",
    [
        ProjectLineageGraphTestCase(
            description="traces upstream and downstream through linear project graph",
            expected_trace=("b.id->c.id", "a.id->b.id"),
            expected_consumers=("a.id->b.id",),
            expected_downstream_trace=("a.id->b.id", "b.id->c.id"),
        )
    ],
    ids=["traces upstream and downstream through linear project graph"],
)
def test_given_linear_project_when_tracing_column_lineage_then_returns_expected_edges(
    test_case: ProjectLineageGraphTestCase,
) -> None:
    project: CompiledProject = make_compiled_project(
        models=(
            make_compiled_model(name="a", query_sql="SELECT 1 AS id", inferred_columns=("id",)),
            make_compiled_model(
                name="b", query_sql='SELECT id FROM __ref("a")', inferred_columns=("id",)
            ),
            make_compiled_model(
                name="c", query_sql='SELECT id FROM __ref("b")', inferred_columns=("id",)
            ),
        )
    )

    result: ProjectColumnLineage | None = build_project_column_lineage(project)

    assert result is not None
    trace: tuple[str, ...] = tuple(
        edge_label(
            edge.source.resource_name,
            edge.source.column_name,
            edge.target.resource_name,
            edge.target.column_name,
        )
        for edge in result.trace_column("c", "id")
    )
    consumers: tuple[str, ...] = tuple(
        edge_label(
            edge.source.resource_name,
            edge.source.column_name,
            edge.target.resource_name,
            edge.target.column_name,
        )
        for edge in result.column_consumers("a", "id")
    )
    downstream_trace: tuple[str, ...] = tuple(
        edge_label(
            edge.source.resource_name,
            edge.source.column_name,
            edge.target.resource_name,
            edge.target.column_name,
        )
        for edge in result.trace_column_downstream("a", "id")
    )
    assert trace == test_case.expected_trace
    assert consumers == test_case.expected_consumers
    assert downstream_trace == test_case.expected_downstream_trace


@pytest.mark.parametrize(
    "test_case",
    [
        SqlglotDisabledLineageTestCase(
            description="returns no lineage when SQLGlot analysis is disabled",
            sqlglot_enabled=False,
            expected_result_is_none=True,
        )
    ],
    ids=["returns no lineage when SQLGlot analysis is disabled"],
)
def test_given_sqlglot_disabled_when_building_column_lineage_then_returns_no_lineage(
    test_case: SqlglotDisabledLineageTestCase,
) -> None:
    project: CompiledProject = make_compiled_project(
        models=(
            make_compiled_model(
                name="orders_out",
                query_sql='SELECT order_id FROM __ref("orders")',
                inferred_columns=("order_id",),
            ),
        ),
        sqlglot_enabled=test_case.sqlglot_enabled,
    )

    result: ProjectColumnLineage | None = build_project_column_lineage(project)

    assert (result is None) is test_case.expected_result_is_none
