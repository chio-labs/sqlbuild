"""Tests for ref reference resolution."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models import CompiledObjectKey, CompiledRelationTarget
from sqlbuild.compiler.compile.types import CompiledResourceType
from sqlbuild.compiler.planner.helpers.resolve.refs import (
    apply_deferred_targets,
    resolve_dbt_ref_references,
    resolve_ref_references,
)
from sqlbuild.compiler.planner.models import CursorBounds
from tests.unit.src.sqlbuild.compiler.planner.helpers.resolve._test_types import (
    ApplyDeferredTargetsTestCase,
    RefResolutionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.resolve.helpers import (
    build_target,
)

_MODEL_TARGETS: dict[str, CompiledRelationTarget] = {
    "orders": CompiledRelationTarget(
        database=None, schema="staging", name="orders", qualified_name="staging.orders"
    ),
    "customers": CompiledRelationTarget(
        database=None, schema="staging", name="customers", qualified_name="staging.customers"
    ),
}

_SEED_TARGETS: dict[str, CompiledRelationTarget] = {
    "country_codes": CompiledRelationTarget(
        database=None, schema="seeds", name="country_codes", qualified_name="seeds.country_codes"
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
        description="resolves seed ref from seed targets",
        query_sql='SELECT * FROM __ref("country_codes")',
        expected_sql="SELECT * FROM seeds.country_codes",
    ),
]

WITH_CURSOR_TEST_CASES: list[RefResolutionTestCase] = [
    RefResolutionTestCase(
        description="wraps ref in cursor-filtered subquery",
        query_sql='SELECT * FROM __ref("orders")',
        expected_sql=(
            "SELECT * FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= '2024-01-15'"
            " AND event_time < '2024-02-01')"
        ),
    ),
    RefResolutionTestCase(
        description="only wraps refs that have cursor inputs",
        query_sql=(
            'SELECT a.*, b.* FROM __ref("orders") a JOIN __ref("customers") b ON a.id = b.id'
        ),
        expected_sql=(
            "SELECT a.*, b.* FROM (SELECT * FROM staging.orders"
            " WHERE event_time >= '2024-01-15'"
            " AND event_time < '2024-02-01') a "
            "JOIN staging.customers b ON a.id = b.id"
        ),
    ),
]

_CURSOR_BOUNDS: CursorBounds = CursorBounds(start="2024-01-15", end="2024-02-01")
_CURSOR_INPUTS: dict[str, str] = {"orders": "event_time"}


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
        model_targets=_MODEL_TARGETS,
        seed_targets=_SEED_TARGETS,
        cursor_bounds=None,
        cursor_inputs={},
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
        model_targets=_MODEL_TARGETS,
        seed_targets=_SEED_TARGETS,
        cursor_bounds=_CURSOR_BOUNDS,
        cursor_inputs=_CURSOR_INPUTS,
    )

    assert result == test_case.expected_sql


@pytest.mark.parametrize(
    "test_case",
    [
        RefResolutionTestCase(
            description="leaves dbt ref unchanged as stub",
            query_sql='SELECT * FROM __dbt_ref("external_model")',
            expected_sql='SELECT * FROM __dbt_ref("external_model")',
        ),
    ],
    ids=["leaves dbt ref unchanged as stub"],
)
def test_given_dbt_ref_when_resolving_then_leaves_unchanged(
    test_case: RefResolutionTestCase,
) -> None:
    result: str = resolve_dbt_ref_references(query_sql=test_case.query_sql)

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
def test_given_deferred_targets_when_applying_then_replaces_expected_targets(
    test_case: ApplyDeferredTargetsTestCase,
) -> None:
    model_targets: dict[str, CompiledRelationTarget] = {
        name: build_target(q, name) for name, q in test_case.model_target_qualified.items()
    }
    seed_targets: dict[str, CompiledRelationTarget] = {
        name: build_target(q, name) for name, q in test_case.seed_target_qualified.items()
    }
    deferred: dict[str, CompiledRelationTarget] = {
        name: build_target(q, name) for name, q in test_case.deferred_qualified.items()
    }
    selected_keys: frozenset[CompiledObjectKey] = frozenset(
        CompiledObjectKey(resource_type=CompiledResourceType.MODEL, name=n)
        for n in test_case.selected_names
    )

    apply_deferred_targets(
        model_targets=model_targets,
        seed_targets=seed_targets,
        deferred_targets=deferred,
        selected_keys=selected_keys,
    )

    result_model_qualified: dict[str, str | None] = {
        name: t.qualified_name for name, t in model_targets.items()
    }
    result_seed_qualified: dict[str, str | None] = {
        name: t.qualified_name for name, t in seed_targets.items()
    }
    assert result_model_qualified == test_case.expected_model_qualified
    assert result_seed_qualified == test_case.expected_seed_qualified
