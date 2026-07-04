"""Tests for cursor upstream qualified name resolution with deferred locations."""

from __future__ import annotations

import pytest

from sqlbuild.compiler.compile.models.core import (
    CompiledModel,
    CompiledRelationLocation,
    CompileSqlReference,
)
from sqlbuild.compiler.planner.helpers.warehouse.snapshot import (
    _resolve_upstream_qualified_name,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers._test_types import (
    CursorUpstreamResolutionTestCase,
)
from tests.unit.src.sqlbuild.compiler.planner.helpers.helpers import (
    PlannerTestAdapter,
    build_cursor_deferred_locations,
    build_cursor_model_map,
    build_cursor_ref,
)


@pytest.mark.parametrize(
    "test_case",
    [
        CursorUpstreamResolutionTestCase(
            description="non-deferred ref resolves to model target",
            ref_name="orders",
            model_qualified_name="staging.orders",
            deferred_qualified_name=None,
            selected_names=None,
            expected_qualified_name="staging.orders",
        ),
        CursorUpstreamResolutionTestCase(
            description="deferred non-selected ref resolves to deferred target",
            ref_name="orders",
            model_qualified_name="dev.orders",
            deferred_qualified_name="prod.orders",
            selected_names=frozenset({"fact_orders"}),
            expected_qualified_name="prod.orders",
        ),
        CursorUpstreamResolutionTestCase(
            description="deferred selected ref resolves to current target not deferred",
            ref_name="orders",
            model_qualified_name="dev.orders",
            deferred_qualified_name="prod.orders",
            selected_names=frozenset({"orders", "fact_orders"}),
            expected_qualified_name="dev.orders",
        ),
        CursorUpstreamResolutionTestCase(
            description="deferred with no selected_names uses deferred target",
            ref_name="orders",
            model_qualified_name="dev.orders",
            deferred_qualified_name="prod.orders",
            selected_names=None,
            expected_qualified_name="prod.orders",
        ),
    ],
    ids=lambda case: case.description,
)
def test_given_ref_and_deferred_locations_when_resolving_upstream_then_returns_expected(
    test_case: CursorUpstreamResolutionTestCase,
) -> None:
    ref: CompileSqlReference = build_cursor_ref(test_case.ref_name)
    model_map: dict[str, CompiledModel] = build_cursor_model_map(
        test_case.ref_name,
        test_case.model_qualified_name,
    )
    deferred_locations: dict[str, CompiledRelationLocation] | None = (
        build_cursor_deferred_locations(
            test_case.ref_name,
            test_case.deferred_qualified_name,
        )
    )

    result: str | None = _resolve_upstream_qualified_name(
        ref=ref,
        adapter=PlannerTestAdapter(),
        model_map=model_map,
        source_map={},
        deferred_locations=deferred_locations,
        selected_names=test_case.selected_names,
    )

    assert result == test_case.expected_qualified_name
