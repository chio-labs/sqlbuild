"""Tests for ref reference resolution."""

from __future__ import annotations

import pytest

from sqlbuild.adapter.shared.types import CursorKind
from sqlbuild.adapters.duckdb.client import DuckDbAdapter
from sqlbuild.compiler.compile.models.core import (
    CompiledObjectKey,
    CompiledRelationLocation,
)
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.resolve.refs import (
    apply_deferred_locations,
    resolve_dbt_ref_references,
    resolve_ref_references,
    resolve_table_function_references,
    resolve_udf_references,
)
from sqlbuild.compiler.planner.models import CursorBounds
from sqlbuild.integrations.dbt.helpers.manifest.compile_refs import DbtCompileReferenceResolver
from sqlbuild.integrations.dbt.helpers.manifest.core import build_dbt_manifest_index
from sqlbuild.integrations.dbt.manifest.models import DbtManifestIndex
from tests.unit.src.sqlbuild.compiler.planner.helpers.resolve._test_types import (
    ApplyDeferredTargetsTestCase,
    RefResolutionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.resolve.helpers import (
    BracketTableFunctionCallAdapter,
    BracketUdfCallAdapter,
    build_target,
)
from tests.unit.src.sqlbuild.integrations.dbt.helpers import (
    build_manifest_data,
    build_manifest_model_node,
)

_MODEL_TARGETS: dict[str, CompiledRelationLocation] = {
    "orders": CompiledRelationLocation(
        database=None, schema="staging", name="orders", qualified_name="staging.orders"
    ),
    "customers": CompiledRelationLocation(
        database=None, schema="staging", name="customers", qualified_name="staging.customers"
    ),
}

_SEED_TARGETS: dict[str, CompiledRelationLocation] = {
    "country_codes": CompiledRelationLocation(
        database=None, schema="seeds", name="country_codes", qualified_name="seeds.country_codes"
    ),
}

_FUNCTION_TARGETS: dict[str, CompiledRelationLocation] = {
    "customer_orders": CompiledRelationLocation(
        database=None,
        schema="analytics",
        name="customer_orders",
        qualified_name="analytics.customer_orders",
    ),
    "format_cents": CompiledRelationLocation(
        database=None,
        schema="analytics",
        name="format_cents",
        qualified_name="analytics.format_cents",
    ),
}

NO_CURSOR_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="replaces ref with qualified name",
        query_sql='SELECT * FROM __ref("orders")',
        expected_sql="SELECT * FROM staging.orders",
    ),
    RefResolutionTestCase(
        description="replaces multiple refs in one query",
        query_sql=(
            'SELECT a.*, b.* FROM __ref("orders") a JOIN __ref("customers") b ON a.id = b.id'
        ),
        expected_sql=(
            "SELECT a.*, b.* FROM staging.orders a JOIN staging.customers b ON a.id = b.id"
        ),
    ),
    RefResolutionTestCase(
        description="leaves unknown ref unchanged",
        query_sql='SELECT * FROM __ref("unknown_model")',
        expected_sql='SELECT * FROM __ref("unknown_model")',
    ),
    RefResolutionTestCase(
        description="resolves seed marker from seed locations",
        query_sql='SELECT * FROM __seed("country_codes")',
        expected_sql="SELECT * FROM seeds.country_codes",
    ),
    RefResolutionTestCase(
        description="leaves seed name through ref unresolved",
        query_sql='SELECT * FROM __ref("country_codes")',
        expected_sql='SELECT * FROM __ref("country_codes")',
    ),
]

WITH_CURSOR_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="wraps ref in cursor-filtered subquery",
        query_sql='SELECT * FROM __ref("orders")',
        expected_sql=(
            "SELECT * FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= TIMESTAMP '2024-01-15'"
            " AND event_time < TIMESTAMP '2024-02-01')"
        ),
        cursor_type=CursorKind.TIMESTAMP,
    ),
    RefResolutionTestCase(
        description="only wraps refs that have cursor inputs",
        query_sql=(
            'SELECT a.*, b.* FROM __ref("orders") a JOIN __ref("customers") b ON a.id = b.id'
        ),
        expected_sql=(
            "SELECT a.*, b.* FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= TIMESTAMP '2024-01-15'"
            " AND event_time < TIMESTAMP '2024-02-01') a "
            "JOIN staging.customers b ON a.id = b.id"
        ),
        cursor_type=CursorKind.TIMESTAMP,
    ),
    RefResolutionTestCase(
        description="renders integer cursor bounds without quotes",
        query_sql='SELECT * FROM __ref("orders")',
        expected_sql=(
            "SELECT * FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= 10"
            " AND event_time < 20)"
        ),
        cursor_type=CursorKind.INTEGER,
    ),
]

TABLE_FUNCTION_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="replaces table function marker with qualified call",
        query_sql='SELECT * FROM __table_fn("customer_orders")(42)',
        expected_sql="SELECT * FROM analytics.customer_orders(42)",
    ),
    RefResolutionTestCase(
        description="replaces table function marker with nested argument suffix",
        query_sql='SELECT * FROM __table_fn("customer_orders")(COALESCE(42, 7))',
        expected_sql="SELECT * FROM analytics.customer_orders(COALESCE(42, 7))",
    ),
    RefResolutionTestCase(
        description="leaves unknown table function marker unchanged",
        query_sql='SELECT * FROM __table_fn("missing")(42)',
        expected_sql='SELECT * FROM __table_fn("missing")(42)',
    ),
    RefResolutionTestCase(
        description="leaves table function marker without call suffix unchanged",
        query_sql='SELECT * FROM __table_fn("customer_orders")',
        expected_sql='SELECT * FROM __table_fn("customer_orders")',
    ),
]

UDF_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="replaces scalar udf marker with default qualified call",
        query_sql='SELECT __udf("format_cents")(amount_cents) AS amount',
        expected_sql="SELECT analytics.format_cents(amount_cents) AS amount",
    ),
    RefResolutionTestCase(
        description="replaces scalar udf marker with nested argument suffix",
        query_sql=('SELECT __udf("format_cents")(COALESCE(a, b), CAST(c AS DECIMAL(10, 2)))'),
        expected_sql=("SELECT analytics.format_cents(COALESCE(a, b), CAST(c AS DECIMAL(10, 2)))"),
    ),
    RefResolutionTestCase(
        description="leaves unknown scalar udf marker unchanged",
        query_sql='SELECT __udf("missing")(amount_cents) AS amount',
        expected_sql='SELECT __udf("missing")(amount_cents) AS amount',
    ),
    RefResolutionTestCase(
        description="leaves scalar udf marker without call suffix unchanged",
        query_sql='SELECT __udf("format_cents") AS amount',
        expected_sql='SELECT __udf("format_cents") AS amount',
    ),
]

DBT_REF_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="replaces one arg dbt ref with manifest relation",
        query_sql='SELECT * FROM __dbt_ref("external_model")',
        expected_sql="SELECT * FROM analytics.external_model",
    ),
    RefResolutionTestCase(
        description="replaces package qualified dbt ref with manifest relation",
        query_sql='SELECT * FROM __dbt_ref("stripe", "orders")',
        expected_sql="SELECT * FROM stripe.orders",
    ),
]

_CURSOR_BOUNDS: CursorBounds = CursorBounds(start="2024-01-15", end="2024-02-01")
_INTEGER_CURSOR_BOUNDS: CursorBounds = CursorBounds(start="10", end="20")
_CURSOR_INPUTS: dict[str, str] = {"orders": "event_time"}
_DBT_MANIFEST: DbtManifestIndex = build_dbt_manifest_index(
    raw_data=build_manifest_data(
        nodes=(
            build_manifest_model_node(
                unique_id="model.analytics.external_model",
                package_name="analytics",
                name="external_model",
                relation_name="analytics.external_model",
            ),
            build_manifest_model_node(
                unique_id="model.stripe.orders",
                package_name="stripe",
                name="orders",
                relation_name="stripe.orders",
            ),
        )
    )
)
_DBT_RESOLVER: DbtCompileReferenceResolver = DbtCompileReferenceResolver(dbt_manifest=_DBT_MANIFEST)


@pytest.mark.parametrize(
    "test_case",
    NO_CURSOR_TEST_CASES,
    ids=[case.description for case in NO_CURSOR_TEST_CASES],
)
def test_given_refs_without_cursor_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_ref_references(
        query_sql=test_case.query_sql,
        model_locations=_MODEL_TARGETS,
        seed_locations=_SEED_TARGETS,
        cursor_bounds=None,
        cursor_inputs={},
        adapter=DuckDbAdapter(),
        cursor_type=None,
        lower_bound_inclusive=True,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    WITH_CURSOR_TEST_CASES,
    ids=[case.description for case in WITH_CURSOR_TEST_CASES],
)
def test_given_refs_with_cursor_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_ref_references(
        query_sql=test_case.query_sql,
        model_locations=_MODEL_TARGETS,
        seed_locations=_SEED_TARGETS,
        cursor_bounds=(
            _INTEGER_CURSOR_BOUNDS
            if test_case.cursor_type == CursorKind.INTEGER
            else _CURSOR_BOUNDS
        ),
        cursor_inputs=_CURSOR_INPUTS,
        adapter=DuckDbAdapter(),
        cursor_type=test_case.cursor_type,
        lower_bound_inclusive=True,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RefResolutionTestCase(
            description="wraps ref in exclusive cursor-filtered subquery for append",
            query_sql='SELECT * FROM __ref("orders")',
            expected_sql=(
                "SELECT * FROM (SELECT * FROM staging.orders"
                " WHERE event_time > TIMESTAMP '2024-01-15'"
                " AND event_time < TIMESTAMP '2024-02-01')"
            ),
            cursor_type=CursorKind.TIMESTAMP,
        )
    ],
    ids=["wraps ref in exclusive cursor-filtered subquery for append"],
)
def test_given_refs_with_exclusive_cursor_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_ref_references(
        query_sql=test_case.query_sql,
        model_locations=_MODEL_TARGETS,
        seed_locations=_SEED_TARGETS,
        cursor_bounds=_CURSOR_BOUNDS,
        cursor_inputs=_CURSOR_INPUTS,
        adapter=DuckDbAdapter(),
        cursor_type=test_case.cursor_type,
        lower_bound_inclusive=False,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    DBT_REF_TEST_CASES,
    ids=[case.description for case in DBT_REF_TEST_CASES],
)
def test_given_dbt_ref_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_dbt_ref_references(
        query_sql=test_case.query_sql,
        external_sql_reference_resolver=_DBT_RESOLVER,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    TABLE_FUNCTION_TEST_CASES,
    ids=[case.description for case in TABLE_FUNCTION_TEST_CASES],
)
def test_given_table_function_marker_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_table_function_references(
        query_sql=test_case.query_sql,
        function_locations=_FUNCTION_TARGETS,
        adapter=DuckDbAdapter(),
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    UDF_TEST_CASES,
    ids=[case.description for case in UDF_TEST_CASES],
)
def test_given_udf_marker_when_resolving_then_returns_expected_sql(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_udf_references(
        query_sql=test_case.query_sql,
        function_locations=_FUNCTION_TARGETS,
        adapter=DuckDbAdapter(),
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RefResolutionTestCase(
            description="renders scalar udf calls through adapter seam",
            query_sql='SELECT __udf("format_cents")(amount_cents) AS amount',
            expected_sql="SELECT analytics.format_cents[amount_cents] AS amount",
        )
    ],
    ids=["renders scalar udf calls through adapter seam"],
)
def test_given_custom_adapter_when_resolving_udf_marker_then_uses_adapter_rendering(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_udf_references(
        query_sql=test_case.query_sql,
        function_locations=_FUNCTION_TARGETS,
        adapter=BracketUdfCallAdapter(),
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RefResolutionTestCase(
            description="renders table function calls through adapter seam",
            query_sql='SELECT * FROM __table_fn("customer_orders")(42)',
            expected_sql="SELECT * FROM TABLE(analytics.customer_orders[42])",
        )
    ],
    ids=["renders table function calls through adapter seam"],
)
def test_given_custom_adapter_when_resolving_table_function_marker_then_uses_adapter_rendering(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_table_function_references(
        query_sql=test_case.query_sql,
        function_locations=_FUNCTION_TARGETS,
        adapter=BracketTableFunctionCallAdapter(),
    )

    assert result == test_case.expected_sql


APPLY_DEFERRED_TEST_CASES: list[ApplyDeferredTargetsTestCase] = [
    ApplyDeferredTargetsTestCase(
        description="replaces non-selected model target with deferred target",
        model_target_qualified={"a": "dev.a", "b": "dev.b"},
        seed_target_qualified={},
        deferred_qualified={"a": "prod.a", "b": "prod.b"},
        selected_names=("b",),
        expected_model_qualified={"a": "prod.a", "b": "dev.b"},
    ),
    ApplyDeferredTargetsTestCase(
        description="does not replace selected model target",
        model_target_qualified={"a": "dev.a"},
        seed_target_qualified={},
        deferred_qualified={"a": "prod.a"},
        selected_names=("a",),
        expected_model_qualified={"a": "dev.a"},
    ),
    ApplyDeferredTargetsTestCase(
        description="replaces non-selected seed target with deferred target",
        model_target_qualified={},
        seed_target_qualified={"countries": "dev.countries"},
        deferred_qualified={"countries": "prod.countries"},
        selected_names=(),
        expected_model_qualified={},
        expected_seed_qualified={"countries": "prod.countries"},
    ),
]


@pytest.mark.parametrize(
    "test_case",
    APPLY_DEFERRED_TEST_CASES,
    ids=[case.description for case in APPLY_DEFERRED_TEST_CASES],
)
def test_given_deferred_locations_when_applying_then_replaces_expected_locations(
    test_case: ApplyDeferredTargetsTestCase,
) -> None:
    model_locations: dict[str, CompiledRelationLocation] = {
        name: build_target(q, name) for name, q in test_case.model_target_qualified.items()
    }
    seed_locations: dict[str, CompiledRelationLocation] = {
        name: build_target(q, name) for name, q in test_case.seed_target_qualified.items()
    }
    deferred: dict[str, CompiledRelationLocation] = {
        name: build_target(q, name) for name, q in test_case.deferred_qualified.items()
    }
    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=n)
        for n in test_case.selected_names
    )

    apply_deferred_locations(
        model_locations=model_locations,
        seed_locations=seed_locations,
        deferred_locations=deferred,
        selected_keys=selected_keys,
    )

    result_model_qualified: dict[str, str | None] = {
        name: t.qualified_name for name, t in model_locations.items()
    }
    result_seed_qualified: dict[str, str | None] = {
        name: t.qualified_name for name, t in seed_locations.items()
    }
    assert result_model_qualified == test_case.expected_model_qualified
    assert result_seed_qualified == test_case.expected_seed_qualified
